"""Supervise envoy processes.

It exposes a local JSON/RPC endpoint for controlling envoy processes; it
does not expose the "standard" Cap'n Proto over nanomsg at the moment
because this endpoint is expected to be used by ops script, and unlike
our "standard" servers, it does not speak Cap'n Proto over nanomsg at
the moment.
"""

__all__ = [
    'main',
]

from concurrent import futures
from pathlib import Path
import json
import logging
import os
import signal
import subprocess
import tempfile
import threading

from garage import asserts
from garage import cli
from garage import components
from garage.http import legacy
from garage.threads import actors
from garage.threads import queues
from garage.threads import signals

from startup import startup


API_NAME = 'envoy-supervisor'
API_VERSION = 0


LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())


ACTOR = components.Fqname(__name__, 'actor')
ACTORS = components.Fqname(__name__, 'actors')


@startup
def collect_actors(actor_stubs: [ACTOR]) -> ACTORS:
    return actor_stubs


class SignalQueueComponent(components.Component):

    require = components.EXIT_STACK

    provide = components.make_fqname_tuple(__name__, 'signal_queue')

    def make(self, require):

        # The default SIGCHLD handler is SIG_IGN, and we need to
        # uninstall that.
        require.exit_stack.enter_context(
            signals.uninstall_handlers(signal.SIGCHLD))

        signal_queue = signals.SignalQueue()
        require.exit_stack.callback(signal_queue.close)

        return signal_queue


class ApiServerComponent(components.Component):

    require = components.make_fqname_tuple(
        __name__,
        components.ARGS,
        components.EXIT_STACK,
        'request_queue',
    )

    provide = ACTOR

    def add_arguments(self, parser):
        group = parser.add_argument_group(__name__ + '/server')
        group.add_argument(
            '--listen', type=int, metavar='PORT', default=8000,
            help='set port for controller interface (default to %(default)d)',
        )
        group.add_argument(
            '--timeout', type=int, default=2,
            help='set request timeout (default to %(default)d seconds)',
        )

    def make(self, require):
        server = legacy.api_server(
            name=API_NAME, version=str(API_VERSION),
            address=('127.0.0.1', require.args.listen),
            request_queue=require.request_queue,
            request_timeout=require.args.timeout,
        )
        require.exit_stack.callback(wait_actor, server)
        return server


class ApiHandlerComponent(components.Component):

    require = components.make_fqname_tuple(
        __name__,
        components.EXIT_STACK,
        'signal_queue',
        'supervisor',
    )

    provide = components.make_fqname_tuple(
        __name__,
        ACTOR,
        'request_queue',
    )

    def make(self, require):

        # At the moment we just use a plain queue.
        request_queue = queues.Queue()
        require.exit_stack.callback(request_queue.close)

        handler = api_handler(
            request_queue=request_queue,
            signal_queue=require.signal_queue,
            supervisor=require.supervisor,
        )
        require.exit_stack.callback(wait_actor, handler)

        return handler, request_queue


class SupervisorComponent(components.Component):

    require = components.ARGS

    provide = components.make_fqname_tuple(__name__, 'supervisor')

    def add_arguments(self, parser):
        group = parser.add_argument_group(__name__ + '/supervisor')
        group.add_argument(
            '--envoy', type=Path, metavar='PATH',
            default=Path('/usr/local/bin/envoy'),
            help='provide path to envoy binary (default to %(default)s)',
        )
        group.add_argument(
            '--envoy-arg', metavar='ARG', action='append',
            help='add envoy argument as: --envoy-arg=--arg=value',
        )

    def check_arguments(self, parser, args):
        if not args.envoy.is_file():
            parser.error('--envoy expect a file: %s' % args.envoy)

    def make(self, require):
        return EnvoySupervisor(
            envoy_path=require.args.envoy,
            envoy_args=require.args.envoy_arg or (),
        )


@cli.command(API_NAME)
@cli.component(ApiHandlerComponent)
@cli.component(ApiServerComponent)
@cli.component(SignalQueueComponent)
def main(actor_stubs: ACTORS,
         request_queue: ApiHandlerComponent.provide.request_queue,
         signal_queue: SignalQueueComponent.provide.signal_queue):
    try:
        # Wait for any actor exits.
        futs = [actor_stub._get_future() for actor_stub in actor_stubs]
        next(futures.as_completed(futs))
    except KeyboardInterrupt:
        LOG.info('user requests shutdown')
    finally:
        request_queue.close()
        signal_queue.close()
    return 0


@actors.OneShotActor.from_func
def api_handler(*, request_queue, signal_queue, supervisor):

    LOG.info('start serving requests')

    with supervisor:

        # Whitelist methods that can be called from remote.
        methods = {
            'spawn': supervisor.spawn,
            'check_terminated': supervisor.check_terminated,
        }

        #
        # The api_handler actor handles two queues simultaneously (it
        # achieves this by busy polling the queues).  While this might
        # not be the most elegant solution, it is probably better than
        # spawning another thread just for pumping items from the signal
        # queue to the request queue.
        #

        while not supervisor.done:

            # Handle signal - don't block on it.

            try:
                signum = signal_queue.get(block=False)
            except queues.Empty:
                pass
            except queues.Closed:
                break
            else:
                LOG.info('receive signal: %s', signum)
                supervisor.handle_signal(signum)

            # Handle incoming requests - block on it for 0.5 seconds.

            try:
                request, response_future = request_queue.get(timeout=0.5)
            except queues.Empty:
                continue
            except queues.Closed:
                break

            if not response_future.set_running_or_notify_cancel():
                LOG.debug('request is cancelled: %r', request)
                continue

            method_name = request.get('method')
            LOG.info('request: %r', method_name)

            try:
                method = methods[method_name]
            except KeyError:
                response_future.set_result({
                    'error': {
                        'type': 'UnrecognizableRequest',
                        'args': (method_name,)
                    },
                })
                continue

            try:
                named_args = request.get('args', {})
                if LOG.isEnabledFor(logging.DEBUG):
                    LOG.debug('request args: %r', named_args)
                ret = method(**named_args)
            except Exception as exc:
                response_future.set_result({
                    'error': {
                        'type': exc.__class__.__name__,
                        'args': exc.args,
                    },
                })
            else:
                if LOG.isEnabledFor(logging.DEBUG):
                    LOG.debug('response: %r', ret)
                response_future.set_result({
                    'return': ret,
                })

    LOG.info('exit')


class EnvoySupervisor:

    def __init__(self, *, envoy_path, envoy_args):
        self.done = False
        self._envoy_path = str(envoy_path.resolve())
        self._envoy_args = []
        for arg in envoy_args:
            # While we use `=` here, note that envoy doesn't accept `=`
            # in an argument though.
            if '=' in arg:
                self._envoy_args.extend(arg.rsplit('=', 1))
            else:
                self._envoy_args.append(arg)
        self._restart_epoch = 0
        self._proc_entries = []

    def __enter__(self):
        asserts.precond(not self.done, 'supervisor is done')
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        """Stop all child processes and clean up all resources."""
        self.done = True
        self._proc_entries, proc_entries = [], self._proc_entries
        for proc_entry in proc_entries:
            proc_entry.close()

    def spawn(self, *, config):
        """Spawn a new child process."""
        asserts.precond(not self.done, 'supervisor is done')

        proc = config_path = None
        try:
            try:
                fd, config_path = tempfile.mkstemp(
                    prefix='config-',
                    suffix='.json',
                )
                os.close(fd)  # Close fd immediately (don't leak it!).

                with open(config_path, 'w') as config_file:
                    json.dump(config, config_file)

                proc = self._start_envoy(config_path)
                pid = proc.pid

                self._proc_entries.append(EnvoyProcEntry(proc, config_path))

                proc = config_path = None

                return {'pid': pid}

            finally:
                if proc is not None:
                    wait_proc(proc)
        finally:
            if config_path is not None:
                os.remove(config_path)

    def handle_signal(self, signum):
        if signum is signal.Signals.SIGCHLD:
            try:
                self.check_terminated()
            except Exception:
                LOG.exception('err while check terminated')

    def check_terminated(self):
        """Check for terminated child processes."""
        asserts.precond(not self.done, 'supervisor is done')

        if not self._proc_entries:
            return {}

        i = 0
        num_terminated = 0
        while i < len(self._proc_entries):
            proc = self._proc_entries[i].proc
            ret = proc.poll()
            if ret is None:
                i += 1
                continue
            LOG.info('envoy is terminated: pid=%d return=%d', proc.pid, ret)
            self._proc_entries.pop(i).close()
            num_terminated += 1

        if not self._proc_entries:
            LOG.info('all processes are terminated')
            self.done = True

        return {'num_terminated': num_terminated}

    def _start_envoy(self, config_path):
        """Start a new envoy process."""

        restart_epoch = self._restart_epoch
        self._restart_epoch += 1

        cmd = [
            self._envoy_path,
            '--config-path', str(config_path),
            '--restart-epoch', str(restart_epoch),
        ]
        cmd.extend(self._envoy_args)
        if LOG.isEnabledFor(logging.DEBUG):
            LOG.debug('spawn: %s', ' '.join(cmd))

        proc = subprocess.Popen(cmd)
        LOG.info(
            'envoy starts: pid=%d restart_epoch=%d',
            proc.pid, restart_epoch,
        )

        return proc


class EnvoyProcEntry:

    def __init__(self, proc, config_path):
        self.proc = proc
        self.config_path = config_path

    def close(self):
        wait_proc(self.proc)
        os.remove(self.config_path)


def wait_actor(actor):
    exc = actor._get_future().exception()
    if exc:
        LOG.error('actor %s has crashed', actor._name, exc_info=exc)


def wait_proc(proc, timeout=5):
    ret = proc.poll()
    if ret is None:
        LOG.info('terminate process: pid=%d', proc.pid)
        proc.terminate()
        ret = proc.wait(timeout=timeout)
    if ret is None:
        LOG.info('kill process: pid=%d', proc.pid)
        proc.kill()
        ret = proc.wait()
    if ret != 0:
        LOG.error('process err: pid=%d return=%d', proc.pid, ret)
