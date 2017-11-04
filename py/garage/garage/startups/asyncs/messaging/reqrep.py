__all__ = [
    'ClientComponent',
]

import functools
import logging

import nanomsg as nn
from nanomsg.curio import Socket

from garage import components
from garage.asyncs import queues
from garage.asyncs.messaging import reqrep
from garage.startups.asyncs.servers import GracefulExitComponent
from garage.startups.asyncs.servers import ServerContainerComponent


#
# XXX This is good for statically-fixed number of client agents (and
# their sockets) that you configure from command-line.  For dynamic
# allocation (you want N agents/sockets, and N is known until runtime),
# we need different mechanism/infrastructure, which I don't have any
# great idea so far.
#
class ClientComponent(components.Component):

    require = (
        components.ARGS,
        components.EXIT_STACK,
        GracefulExitComponent.provide.graceful_exit,
    )

    provide = components.make_fqname_tuple(
        __name__,
        ServerContainerComponent.require.make_server,
        'request_queue',
    )

    def __init__(
            self, *,
            module_name=None, name_prefix=None,
            group=None, arg_prefix=None,
            num_sockets=1,
            queue_capacity=32,
            timeout=2,  # Unit: seconds.
            logger=None):

        if arg_prefix:
            arg_prefix = arg_prefix + '-'
        elif name_prefix:
            arg_prefix = name_prefix.replace('_', '-') + '-'
        else:
            arg_prefix = ''
        self.__arg_prefix = arg_prefix
        self.__attr_prefix = arg_prefix.replace('-', '_')

        if name_prefix:
            name = name_prefix
            name_prefix = name_prefix + '_'
        else:
            name = 'client'
            name_prefix = ''

        if module_name or name_prefix:
            self.provide = components.make_fqname_tuple(
                module_name or __name__,
                ServerContainerComponent.require.make_server,
                '%srequest_queue' % name_prefix,
            )
            self.order = '%s/%s' % (module_name or __name__, name)

        self.__group = '%s/%s' % (group or module_name or __name__, name)

        self.num_sockets = num_sockets
        self.queue_capacity = queue_capacity
        self.timeout = timeout

        self.__logger = logger

    def add_arguments(self, parser):
        group = parser.add_argument_group(self.__group)
        group.add_argument(
            '--%sbind' % self.__arg_prefix,
            metavar='URL', action='append',
            help='bind socket to URL',
        )
        group.add_argument(
            '--%sconnect' % self.__arg_prefix,
            metavar='URL', action='append',
            help='connect socket to URL',
        )
        group.add_argument(
            '--%snum-sockets' % self.__arg_prefix,
            metavar='N', type=int, default=self.num_sockets,
            help='set number of client sockets (default to %(default)s)',
        )
        group.add_argument(
            '--%squeue-capacity' % self.__arg_prefix,
            metavar='L', type=int, default=self.queue_capacity,
            help='set request queue capacity (default to %(default)s)',
        )
        group.add_argument(
            '--%stimeout' % self.__arg_prefix,
            metavar='T', type=float, default=self.timeout,
            help='set request timeout (default to %(default)s seconds)',
        )

    def make(self, require):

        bind = getattr(require.args, '%sbind' % self.__attr_prefix) or ()
        connect = getattr(require.args, '%sconnect' % self.__attr_prefix) or ()
        if not bind and not connect:
            (self.__logger or logging).warning(
                'client socket is neither bound nor connected to any address')

        capacity = getattr(
            require.args, '%squeue_capacity' % self.__attr_prefix)

        # NOTE: Don't use socket timeout (NN_SNDTIMEO and NN_RCVTIMEO)
        # because we are using non-blocking sockets.
        timeout = getattr(require.args, '%stimeout' % self.__attr_prefix)
        if timeout <= 0:
            timeout = None  # No timeout.

        num_sockets = getattr(
            require.args,
            '%snum_sockets' % self.__attr_prefix,
        )

        sockets = []
        for _ in range(num_sockets):

            socket = Socket(protocol=nn.NN_REQ)
            require.exit_stack.enter_context(socket)

            request_queue = queues.Queue(capacity=capacity)
            require.exit_stack.callback(request_queue.close)

            for url in bind:
                socket.bind(url)
            for url in connect:
                socket.connect(url)

            sockets.append(socket)

        return (
            functools.partial(
                reqrep.client,
                graceful_exit=require.graceful_exit,
                sockets=sockets,
                request_queue=request_queue,
                timeout=timeout,
            ),
            request_queue,
        )
