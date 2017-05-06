__all__ = [
    'HttpServerComponent',
]

import functools

import http2

from garage import components
from garage.startups.asyncs.servers import GracefulExitComponent
import garage.asyncs.utils
import garage.http.servers


class HttpServerComponent(components.Component):

    require = (
        GracefulExitComponent.provide.graceful_exit,
        components.ARGS,
    )

    provide = components.make_fqname_tuple(
        __name__,
        'http_server',
        'http_server_scheme',
        'http_server_address',
    )

    def __init__(self, *, module_name=None, name=None, group=None):

        self.__group = group or module_name or garage.http.servers.__name__

        if name:
            self.__arg_prefix = name.replace('_', '-') + '-'
            self.__attr_prefix = name + '_'
        else:
            self.__arg_prefix = ''
            self.__attr_prefix = ''

        if module_name is not None or name is not None:
            module_name = module_name or __name__
            name = name or 'http_server'
            self.provide = components.make_fqname_tuple(
                module_name,
                name,
                name + '_scheme',
                name + '_address',
            )
            self.order = '%s/%s' % (module_name, name)

    def add_arguments(self, parser):
        group = parser.add_argument_group(self.__group)
        group.add_argument(
            '--%shost' % self.__arg_prefix, default='',
            help='set server address (default to all network interfaces)',
        )
        group.add_argument(
            '--%sport' % self.__arg_prefix, type=int, default=8443,
            help='set server port (default to %(default)d)',
        )
        group.add_argument(
            '--%scertificate' % self.__arg_prefix,
            help='set server TLS certificate',
        )
        group.add_argument(
            '--%sprivate-key' % self.__arg_prefix,
            help='set server TLS private key',
        )

    def check_arguments(self, parser, args):
        certificate = getattr(args, self.__attr_prefix + 'certificate')
        private_key = getattr(args, self.__attr_prefix + 'private_key')
        if (certificate is None) != (private_key is None):
            parser.error('require both certificate and private key')

    def make(self, require):

        graceful_exit = require.graceful_exit

        address = (
            getattr(require.args, self.__attr_prefix + 'host'),
            getattr(require.args, self.__attr_prefix + 'port'),
        )
        make_server_socket = functools.partial(
            garage.asyncs.utils.make_server_socket,
            address,
        )

        certificate = getattr(require.args, self.__attr_prefix + 'certificate')
        private_key = getattr(require.args, self.__attr_prefix + 'private_key')
        if certificate and private_key:
            scheme = http2.Scheme.HTTPS
            make_ssl_context = functools.partial(
                http2.make_ssl_context,
                certificate,
                private_key,
            )
        else:
            scheme = http2.Scheme.HTTP
            make_ssl_context = None

        async def http_server(handler, *, logger=None):
            return await garage.asyncs.utils.serve(
                graceful_exit,
                make_server_socket,
                handler,
                make_ssl_context=make_ssl_context,
                logger=logger,
            )

        return (
            http_server,
            scheme,
            address,
        )
