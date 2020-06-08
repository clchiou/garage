"""Start up supervise_agents.

This parts module is unlike others in that it initializes the global
agent_queue, etc., not just provide "part maker" for it.

Basically this parts module provides two queues: an agent_queue for
spawning new agent, and a shutdown_queue for gracefully shutting down
agents.
"""

from startup import startup

from g1.apps import parameters
from g1.apps import utils
from g1.asyncs.bases import locks
from g1.asyncs.bases import queues
from g1.asyncs.bases import tasks
from g1.bases import labels

from .. import agents  # pylint: disable=relative-beyond-top-level

LABELS = labels.make_labels(
    agents.__name__,
    # supervise_agents.
    'supervise_agents',
    'agent_queue',
    'graceful_exit',
    'grace_period',
    # shutdown_agents.
    'shutdown_queue',
)

PARAMS = parameters.define(
    agents.__name__,
    parameters.Namespace(
        grace_period=parameters.Parameter(
            4, type=(int, float), unit='seconds'
        ),
    ),
)

startup.set(LABELS.agent_queue, tasks.CompletionQueue())
startup.set(LABELS.graceful_exit, locks.Event())
startup.set(LABELS.shutdown_queue, queues.Queue())

utils.depend_parameter_for(LABELS.grace_period, PARAMS.grace_period)

utils.define_binder(
    agents.supervise_agents,
    LABELS.supervise_agents,
    {
        'agent_queue': LABELS.agent_queue,
        'graceful_exit': LABELS.graceful_exit,
        'grace_period': LABELS.grace_period,
    },
)


@startup
def spawn_shutdown_agents(
    agent_queue: LABELS.agent_queue,
    graceful_exit: LABELS.graceful_exit,
    shutdown_queue: LABELS.shutdown_queue,
):
    agent_queue.spawn(agents.shutdown_agents(graceful_exit, shutdown_queue))
