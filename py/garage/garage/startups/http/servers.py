"""Template of HttpServerComponent."""

__all__ = [
    'make_http_server_component',
]

from garage import components
from garage.http.servers import ServerConfig


def make_http_server_component(
        *,
        package_name,
        argument_group,
        argument_prefix):

    HOST = '%s_host' % argument_prefix
    PORT = '%s_port' % argument_prefix
    CERTIFICATE = '%s_certificate' % argument_prefix
    PRIVATE_KEY = '%s_private_key' % argument_prefix
    BACKLOG = '%s_backlog' % argument_prefix

    class HttpServerComponent(components.Component):

        require = components.ARGS

        provide = components.make_fqname_tuple(package_name, 'config')

        def add_arguments(self, parser):
            group = parser.add_argument_group(argument_group + '#http')
            group.add_argument(
                '--%s-host' % argument_prefix, dest=HOST,
                action='append',
                help="""add HTTP/2 server address""")
            group.add_argument(
                '--%s-port' % argument_prefix, dest=PORT,
                required=True, type=int,
                help="""set HTTP/2 server port""")
            group.add_argument(
                '--%s-certificate' % argument_prefix, dest=CERTIFICATE,
                help="""set HTTP/2 server certificate""")
            group.add_argument(
                '--%s-private-key' % argument_prefix, dest=PRIVATE_KEY,
                help="""set HTTP/2 server private key""")
            group.add_argument(
                '--%s-backlog' % argument_prefix, dest=BACKLOG,
                type=int, default=ServerConfig.BACKLOG,
                help="""set connection queue size (default to %(default)d)""")

        def check_arguments(self, parser, args):
            certificate = getattr(args, CERTIFICATE)
            private_key = getattr(args, PRIVATE_KEY)
            if (certificate is None) != (private_key is None):
                parser.error('require both certificate and private key')

        def make(self, require):
            args = require.args
            config = ServerConfig()
            config.host = getattr(args, HOST)
            config.port = getattr(args, PORT)
            config.certificate = getattr(args, CERTIFICATE)
            config.private_key = getattr(args, PRIVATE_KEY)
            config.backlog = getattr(args, BACKLOG)
            return config

    return HttpServerComponent
