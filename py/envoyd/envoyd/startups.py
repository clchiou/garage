"""Define actor component.

NOTE: We start actors as soon as Component.make() is called; this could
be inflexible (like, you cannot do two stage startup since it would be
too late at the second stage), but for now, this is good enough.
"""

__all__ = [
    'ControllerComponent',
]

from pathlib import Path
import signal

from garage import components
from garage.http import legacy
from garage.threads import queues
from garage.threads import signals
from garage.startups.logging import LoggingComponent

import envoyd

from . import controllers
from . import utils


API_NAME = 'envoyd'
API_VERSION = 0


class ControllerComponent(components.Component):

    require = (
        components.ARGS,
        components.EXIT_STACK,
        # Ensure that actors are spawned after loggers are configured.
        LoggingComponent.provide.level,
    )

    provide = components.make_fqname_tuple(__name__, 'actors')

    def add_arguments(self, parser):
        group = parser.add_argument_group(envoyd.__name__ + '/controller')
        group.add_argument(
            '--controller-address', metavar='ADDRESS', default='127.0.0.1',
            help='set controller interface address (default to %(default)s)',
        )
        group.add_argument(
            '--controller-port', metavar='PORT', type=int, default=8000,
            help='set controller interface port (default to %(default)d)',
        )
        group.add_argument(
            '--controller-timeout', metavar='SECONDS', type=int, default=2,
            help='set request timeout (default to %(default)d seconds)',
        )
        # Common args for the supervisor.
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
        # HACK: Call the entry point directly (because at this point,
        # cli.CONTEXT is not ready yet).
        args.role._entry_point(parser, args)

    def make(self, require):

        #
        # Make request queue.
        #
        # At the moment we just use a plain queue.
        #

        request_queue = queues.Queue()
        require.exit_stack.callback(request_queue.close)

        #
        # Make signal queue.
        #

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

        #
        # Make supervisor.
        #

        envoy_args = []
        for arg in require.args.envoy_arg or ():
            # While we use `=` here, note that envoy doesn't accept `=`
            # in an argument though.
            if '=' in arg:
                envoy_args.extend(arg.rsplit('=', 1))
            else:
                envoy_args.append(arg)

        supervisor = require.args.make_supervisor(
            args=require.args,
            envoy=require.args.envoy,
            envoy_args=envoy_args,
        )
        require.exit_stack.enter_context(supervisor)

        #
        # Make HTTP server.
        #

        server = legacy.api_server(
            name=API_NAME, version=str(API_VERSION),
            address=(
                require.args.controller_address,
                require.args.controller_port,
            ),
            request_queue=request_queue,
            request_timeout=require.args.controller_timeout,
        )
        require.exit_stack.callback(utils.wait_actor, server)

        #
        # Make controller.
        #

        controller = controllers.controller(
            request_queue=request_queue,
            signal_queue=signal_queue,
            supervisor=supervisor,
        )
        require.exit_stack.callback(utils.wait_actor, controller)

        #
        # NOTE: This is a trick - we push queue.close onto stack at last
        # to guarantee that we close queues before we wait for actors;
        # or we will be trapped in a dead lock.
        #
        require.exit_stack.callback(request_queue.close)
        require.exit_stack.callback(signal_queue.close)

        #
        # Return all actors.
        #

        return (server, controller)
