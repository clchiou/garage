__all__ = [
    'SupervisorInterface',
    'controller',
]

import logging
import signal

from garage.threads import actors
from garage.threads import queues


LOG = logging.getLogger(__name__)


class SupervisorInterface:

    PUBLIC_METHOD_NAMES = ()

    def is_done(self):
        raise NotImplementedError

    def spawn_default(self):
        raise NotImplementedError

    def check_procs(self):
        raise NotImplementedError

    def list_procs(self):
        raise NotImplementedError


@actors.OneShotActor.from_func('con')
def controller(*, request_queue, signal_queue, supervisor):

    LOG.info('start handling controller requests')

    # Launch envoy with the default config.
    ret = supervisor.spawn_default()
    if ret is None:
        LOG.warning('no default envoy is spawned')
    else:
        LOG.info('spawn a default envoy: %r', ret)

    # Construct list of public methods.
    methods = {
        'check_procs': supervisor.check_procs,
        'list_procs': supervisor.list_procs,
    }
    for method_name in supervisor.PUBLIC_METHOD_NAMES:
        methods[method_name] = getattr(supervisor, method_name)

    #
    # The controller processes two queues simultaneously.  It achieves
    # this by busy polling the queues.  While polling might not be the
    # most elegant solution, it is probably better than spawning another
    # thread just for pumping items from the signal queue to the request
    # queue.
    #

    while not supervisor.is_done():

        # Handle signal - don't block on it.

        try:
            signum = signal_queue.get(block=False)
        except queues.Empty:
            pass
        except queues.Closed:
            break
        else:
            handle_signal(signum, supervisor)

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


def handle_signal(signum, supervisor):
    LOG.info('receive signal: %s', signum)
    if signum is signal.Signals.SIGCHLD:
        try:
            supervisor.check_procs()
        except Exception:
            LOG.exception('err while check procs')
    elif signum in (signal.Signals.SIGINT, signal.Signals.SIGTERM):
        LOG.info('shutdown controller')
        raise actors.Exit
