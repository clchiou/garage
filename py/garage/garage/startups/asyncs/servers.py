__all__ = [
    'GracefulExitComponent',
    'ServerContainerComponent',
]

import functools

import curio

from garage import components
from garage.asyncs import servers


class GracefulExitComponent(components.Component):

    GRACEFUL_PERIOD = 5  # Unit: seconds

    provide = components.make_fqname_tuple(__name__, 'graceful_exit')

    def add_arguments(self, parser):
        group = parser.add_argument_group(servers.__name__)
        group.add_argument(
            '--graceful-period',
            default=self.GRACEFUL_PERIOD, type=int,
            help="""set graceful period when terminating servers
                    (default to %(default)s seconds)
                 """)

    def make(self, require):
        return curio.Event()


class ServerContainerComponent(components.Component):

    require = components.make_fqname_tuple(
        __name__,
        components.ARGS,
        GracefulExitComponent.provide.graceful_exit,
        ['make_server'],
    )

    provide = components.make_fqname_tuple(__name__, 'serve')

    def make(self, require):
        return functools.partial(
            servers.serve,
            require.graceful_exit,
            require.args.graceful_period,
            require.make_server,
        )