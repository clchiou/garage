__all__ = [
    'ClientComponent',
]

import nanomsg as nn
from nanomsg.curio import Socket

from garage import components
from garage.asyncs import queues
from garage.asyncs.messaging import reqrep
from garage.startups.asyncs.servers import ServerContainerComponent


class ClientComponent(components.Component):

    require = (
        components.ARGS,
        components.EXIT_STACK,
    )

    provide = components.make_fqname_tuple(
        __name__,
        ServerContainerComponent.require.make_server,
        'get_socket',
        'request_queue',
    )

    def __init__(
            self, *,
            module_name=None, name=None,
            group=None,
            queue_capacity=0,
            logger=None):

        if name:
            self.__arg = name.replace('_', '-') + '-'
            self.__attr = name + '_'
        else:
            self.__arg = ''
            self.__attr = ''

        name = name or 'client'

        if module_name is not None:
            self.provide = components.make_fqname_tuple(
                module_name,
                ServerContainerComponent.require.make_server,
                'get_socket',
                'request_queue',
            )
            self.order = '%s/%s' % (module_name, name)

        self.__group = '%s/%s' % (group or module_name or __name__, name)

        self.__queue_capacity = queue_capacity

        self.__logger = logger

    def add_arguments(self, parser):
        group = parser.add_argument_group(self.__group)
        group.add_argument(
            '--%sbind' % self.__arg, metavar='URL', action='append',
            help='bind socket to the URL',
        )
        group.add_argument(
            '--%sconnect' % self.__arg, metavar='URL', action='append',
            help='connect socket to the URL',
        )
        group.add_argument(
            '--%squeue-capacity' % self.__arg,
            type=int, default=self.__queue_capacity,
            help='set request queue capacity (default to %(default)s)',
        )
        group.add_argument(
            '--%stimeout' % self.__arg, type=float,
            help='set request timeout',
        )

    class Maker:

        def __init__(
                self,
                exit_stack,
                bind_addresses, connect_addresses,
                request_queue,
                timeout):
            self._exit_stack = exit_stack
            self.bind_addresses = bind_addresses
            self.connect_addresses = connect_addresses
            self.request_queue = request_queue
            self.timeout = timeout
            self._socket = None

        def _make(self):
            socket = self._exit_stack.enter_context(Socket(protocol=nn.NN_REQ))
            for url in self.bind_addresses:
                socket.bind(url)
            for url in self.connect_addresses:
                socket.connect(url)
            return socket

        def make_client(self):
            # Although it's called "make_client", we expect that it to
            # be called only once.  If you call it multiple times, each
            # client instance will share the same Socket object (which
            # might not be desirable).
            if self._socket is None:
                self._socket = self._make()
            return reqrep.client(
                self._socket,
                self.request_queue,
                timeout=self.timeout,
            )

        def get_socket(self):
            if self._socket is None:
                self._socket = self._make()
            return self._socket

    def make(self, require):

        bind = getattr(require.args, '%sbind' % self.__attr) or ()
        connect = getattr(require.args, '%sconnect' % self.__attr) or ()
        if not bind and not connect:
            if self.__logger:
                self.__logger.warning(
                    'neither bind nor connect address is provided')

        capacity = getattr(require.args, '%squeue_capacity' % self.__attr)

        timeout = getattr(require.args, '%stimeout' % self.__attr)

        request_queue = queues.Queue(capacity=capacity)

        maker = self.Maker(
            require.exit_stack,
            bind, connect,
            request_queue,
            timeout,
        )

        return (
            maker.make_client,
            maker.get_socket,
            maker.request_queue,
        )
