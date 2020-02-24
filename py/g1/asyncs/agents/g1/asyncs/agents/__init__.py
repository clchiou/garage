"""Agents.

(When we were picking the name, "actor", "agent", and "server" came to
our mind.  All three of them describe certain things that might not be
exactly the same as what is implemented here.  We picked/hijacked the
term "agent" here because "agent" seems to be the least common one.)

Agents are long-running, top-level tasks.  An agent can do anything:
spawn and supervise sub-tasks; serve requests, in which case it is also
called a "server"; perform background jobs.

Usually you will have the application's main function running the agent
supervisor task, as the root of the supervisor tree.
"""

__all__ = [
    'SupervisorError',
    'shutdown_agents',
    'supervise_agents',
]

import contextlib
import logging
import signal

from g1.asyncs.bases import signals
from g1.asyncs.bases import tasks
from g1.asyncs.bases import timers

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())

EXIT_SIGNUMS = (
    signal.SIGINT,
    signal.SIGTERM,
)


class SupervisorError(Exception):
    """Raise when supervisor exits non-gracefully."""


async def supervise_agents(
    agent_queue,
    graceful_exit,
    grace_period,  # Unit: seconds.
):
    """Supervise agents.

    The supervisor starts exiting when any of the following happens:

    * An agent exits normally.
    * An agent errs out (including being cancelled).
    * A signal is delivered.
    * The graceful_exit event is set.

    During the exit:

    * It closes the agent_queue; thus no new agent can be spawned.

    * If it starts exiting due to an agent erring out, it cancels
      remaining agents and exits.

    * Else, it does a graceful exit:
      * It sets the graceful_exit event.
      * It waits for the grace_period.  If during this period, an agent
        errs out or another signal is delivered, it cancels remaining
        agents and exits.
      * After the grace_period, it cancels remaining agents and exits.
    """
    main_task = tasks.get_current_task()
    async with contextlib.AsyncExitStack() as stack:

        def start_exiting():
            if agent_queue.is_closed():
                return False
            agent_queue.close()
            graceful_exit.set()
            stack.enter_context(
                timers.timeout_after(grace_period, task=main_task)
            )
            return True

        signal_source = stack.enter_context(signals.SignalSource())
        for signum in EXIT_SIGNUMS:
            signal_source.enable(signum)

        # Make sure that remaining agents are cancelled on error.
        await stack.enter_async_context(agent_queue)

        internal_tasks = [
            tasks.spawn_onto_stack(
                awaitable, stack, always_cancel=True, log_on_error=False
            ) for awaitable in (
                join_agents(agent_queue, start_exiting),
                request_graceful_exit(graceful_exit, start_exiting),
                receive_signals(signal_source, start_exiting),
            )
        ]
        join_agents_task = internal_tasks[0]

        try:
            async for task in tasks.as_completed(internal_tasks):
                task.get_result_nonblocking()
                if task is join_agents_task:
                    # If all agents are completed, let the supervisor
                    # exit from here since we don't quite care whether
                    # another signal is delivered.
                    break
        except timers.Timeout:
            raise SupervisorError('grace period exceeded') from None


async def join_agents(agent_queue, start_exiting):
    async for agent in agent_queue:
        exc = agent.get_exception_nonblocking()
        if exc:
            if agent_queue.is_closed():
                message = 'agent err out during graceful exit: %r'
            else:
                message = 'agent err out: %r'
            raise SupervisorError(message % agent) from exc
        else:
            if start_exiting():
                LOG.info('graceful exit: agent exit: %r', agent)


async def request_graceful_exit(graceful_exit, start_exiting):
    await graceful_exit.wait()
    if start_exiting():
        LOG.info('graceful exit: requested by user')


async def receive_signals(signal_source, start_exiting):
    signum = await signal_source.get()
    LOG.info('graceful exit: receive signal: %r', signum)
    start_exiting()
    signum = await signal_source.get()
    raise SupervisorError('receive signal during graceful exit: %r' % signum)


async def shutdown_agents(graceful_exit, shutdown_queue):
    """Shut down agents on graceful exit.

    The shutdown_queue is a queue of functions that, when called, shut
    down agents gracefully.  Note that these are only called on graceful
    exit; so you should not use them for cleanup.
    """
    await graceful_exit.wait()
    for shutdown in shutdown_queue.close(graceful=False):
        try:
            shutdown()
        except Exception:
            LOG.exception('shutdown function raises: %s', shutdown)
