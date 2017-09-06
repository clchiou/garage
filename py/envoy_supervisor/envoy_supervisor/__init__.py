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
import functools
import json
import logging
import re
import signal
import subprocess
import threading

from garage import asserts
from garage import cli
from garage import components
from garage.http import legacy
from garage.threads import actors
from garage.threads import queues
from garage.threads import signals

from startup import startup


API_NAME = 'envoy_supervisor'
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

        require.exit_stack.enter_context(signals.uninstall_handlers(
            # The default SIGCHLD handler is SIG_IGN, and we need to
            # uninstall that.
            signal.SIGCHLD,
            # We will handle SIGINT and SIGTERM ourselves.
            signal.SIGINT,
            signal.SIGTERM,
        ))

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
        'make_supervisor',
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
            make_supervisor=require.make_supervisor,
        )
        require.exit_stack.callback(wait_actor, handler)

        return handler, request_queue


class SupervisorComponent(components.Component):

    require = components.ARGS

    provide = components.make_fqname_tuple(__name__, 'make_supervisor')

    def add_arguments(self, parser):
        group = parser.add_argument_group(__name__ + '/supervisor')
        group.add_argument(
            '--config-dir', type=Path, metavar='DIR', required=True,
            help='provide path to config store directory.',
        )
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
        if not args.config_dir.is_dir():
            parser.error('--config-dir expect a dir: %s' % args.config_dir)
        if not args.envoy.is_file():
            parser.error('--envoy expect a file: %s' % args.envoy)

    def make(self, require):
        return functools.partial(
            EnvoySupervisor,
            config_dir=require.args.config_dir,
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
    finally:
        request_queue.close()
        signal_queue.close()
    return 0


@actors.OneShotActor.from_func
def api_handler(*, request_queue, signal_queue, make_supervisor):

    LOG.info('start serving requests')

    with make_supervisor() as supervisor:

        # Launch one with the default config.
        ret = supervisor.spawn_default()
        if ret is None:
            LOG.warning('no default envoy is spawned')
        else:
            LOG.info('spawn a default envoy: %r', ret)

        # Whitelist methods that can be called from remote.
        methods = {
            # Config file management.
            'list_configs': supervisor.list_configs,
            'add_config': supervisor.add_config,
            'remove_config': supervisor.remove_config,
            'set_default_config': supervisor.set_default_config,
            # Envoy process management.
            'list_procs': supervisor.list_procs,
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

    def __init__(self, *, config_dir, envoy_path, envoy_args):

        self.done = False

        self._config_dir = config_dir.resolve()

        self._configs = {}  # Map config name to path.
        for path in self._config_dir.iterdir():
            config_name = EnvoySupervisor._maybe_get_config_name(path)
            if config_name is not None:
                LOG.info('load config: %s', config_name)
                self._configs[config_name] = self._config_dir / path

        self._default = EnvoySupervisor._load_default(self._config_dir)
        LOG.info('default config: %s', self._default)

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

    #
    # Config file management.
    #

    CONFIG_DEFAULT = 'default'

    CONFIG_FILENAME_PREFIX = 'config-'
    CONFIG_FILENAME_SUFFIX = '.json'

    # For now, only permit a narrow set of names.
    CONFIG_NAME_PATTERN = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')

    @classmethod
    def _is_config_name(cls, maybe_name):
        return bool(cls.CONFIG_NAME_PATTERN.fullmatch(maybe_name))

    @classmethod
    def _maybe_get_config_name(cls, maybe_config_path):
        filename = maybe_config_path.name
        if not filename.startswith(cls.CONFIG_FILENAME_PREFIX):
            return None
        if not filename.endswith(cls.CONFIG_FILENAME_SUFFIX):
            return None
        prefix_len = len(cls.CONFIG_FILENAME_PREFIX)
        suffix_len = len(cls.CONFIG_FILENAME_SUFFIX)
        maybe_name = filename[prefix_len:-suffix_len]
        if not cls._is_config_name(maybe_name):
            return None
        # Okay, it is a config file and this is a config name.
        return maybe_name

    @classmethod
    def _load_default(cls, config_dir):
        path = config_dir / cls.CONFIG_DEFAULT
        if not path.is_symlink():
            return None
        return cls._maybe_get_config_name(path.resolve())

    def list_configs(self):
        """List config files."""
        asserts.precond(not self.done, 'supervisor is done')
        return {
            'configs': {
                name: {
                    'path': str(path),
                    'default': name == self._default,
                }
                for name, path in self._configs.items()
            },
        }

    def add_config(self, *, name, config):
        """Add a config file."""
        asserts.precond(not self.done, 'supervisor is done')

        if name in self._configs:
            raise KeyError('refuse to overwrite config: %r' % name)

        if not self._is_config_name(name):
            raise KeyError('not a valid config name: %r' % name)
        config_path = self._to_config_path(name)
        # Sanity check - path should not be "taken".
        asserts.precond(
            not config_path.exists(),
            'expect non-existence: %s', config_path,
        )

        try:
            config_path.write_text(json.dumps(config))
        except Exception:
            config_path.unlink()
            raise

        self._configs[name] = config_path.resolve()

        LOG.info('add config: %s', name)
        return {}

    def remove_config(self, *, name):
        """Remove a config file by name."""
        asserts.precond(not self.done, 'supervisor is done')

        config_path = self._get_config_path(name)

        config_path.unlink()
        self._configs.pop(name)

        if name == self._default:
            # Remove the "default" symlink file (this is optional).
            self._default = None
            try:
                self._default_path.unlink()
            except OSError:
                LOG.warning(
                    'cannot remove default config symlink: %s',
                    self._default_path, exc_info=True,
                )

        LOG.info('remove config: %s', name)
        return {}

    def set_default_config(self, *, name):
        """Set default config name."""
        asserts.precond(not self.done, 'supervisor is done')

        config_path = self._get_config_path(name)

        next_default = self._default_path.with_suffix('.next')
        if next_default.exists():
            next_default.unlink()

        next_default.symlink_to(config_path.name)

        next_default.rename(self._default_path)

        self._default = name

        LOG.info('set default config to: %s', name)
        return {}

    @property
    def _default_path(self):
        return self._config_dir / self.CONFIG_DEFAULT

    def _to_config_path(self, name):
        filename = '%s%s%s' % (
            self.CONFIG_FILENAME_PREFIX,
            name,
            self.CONFIG_FILENAME_SUFFIX,
        )
        return self._config_dir / filename

    def _get_config_path(self, name):
        if not self._is_config_name(name):
            raise KeyError('not a valid config name: %r' % name)
        config_path = self._configs[name]
        asserts.precond(
            config_path.exists(),
            'expect file existence: %s', config_path,
        )
        return config_path

    #
    # Envoy process management.
    #

    def list_procs(self):
        """List supervised child processes."""
        asserts.precond(not self.done, 'supervisor is done')
        return {
            'procs': [
                {
                    'config_name': proc_entry.config_name,
                    'pid': proc_entry.proc.pid,
                    'restart_epoch': proc_entry.restart_epoch,
                }
                for proc_entry in self._proc_entries
            ],
        }

    def spawn_default(self):
        """Spawn a new envoy process with the default config.

        This method is not called from remote.
        """
        if not self._default:
            return None
        return self.spawn(config_name=self._default)

    def spawn(self, *, config_name):
        """Spawn a new envoy process with the given config."""
        asserts.precond(not self.done, 'supervisor is done')

        config_path = self._get_config_path(config_name)

        proc, restart_epoch = self._start_envoy(config_path)
        try:
            pid = proc.pid
            self._proc_entries.append(EnvoyProcEntry(
                config_name=config_name,
                proc=proc,
                restart_epoch=restart_epoch,
            ))
            return {'pid': pid, 'restart_epoch': restart_epoch}
        except Exception:
            wait_proc(proc)
            raise

    def handle_signal(self, signum):
        """Handle signal.

        This method is not called from remote.
        """
        LOG.info('receive signal: %s', signum)
        if signum is signal.Signals.SIGCHLD:
            try:
                self.check_terminated()
            except Exception:
                LOG.exception('err while check terminated')
        elif signum in (signal.Signals.SIGINT, signal.Signals.SIGTERM):
            LOG.info('user requests shutdown')
            raise actors.Exit

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

        return proc, restart_epoch


class EnvoyProcEntry:

    def __init__(self, *, config_name, proc, restart_epoch):
        self.config_name = config_name
        self.proc = proc
        self.restart_epoch = restart_epoch

    def close(self):
        wait_proc(self.proc)


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
