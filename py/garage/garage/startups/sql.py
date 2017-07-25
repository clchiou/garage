__all__ = [
    'EngineComponent',
]

import logging

import garage.sql.sqlite
from garage import components
from garage.startups.logging import LoggingComponent


class EngineComponent(components.Component):

    require = components.ARGS

    provide = components.make_fqname_tuple(__name__, 'engine')

    def __init__(
            self, *,
            module_name=None, name=None,
            group=None, arg=None,
            check_same_thread=False):
        """Create a SQLAlchemy Engine object component.

        NOTE: components.find_closure uses module_name to search for
        component; set it to where this component is instantiated would
        be helpful to find_closure.
        """

        if arg:
            pass
        elif name:
            arg = '--%s-db-url' % name.replace('_', '-')
        else:
            arg = '--db-url'
        self.__arg = arg
        self.__attr = arg[2:].replace('-', '_')

        group = group or module_name or __name__

        if module_name is None and name is None:
            self.__group = '%s/engine' % group
        else:
            module_name = module_name or __name__
            name = name or 'engine'
            self.provide = components.make_fqname_tuple(module_name, name)
            self.order = '%s/%s' % (module_name, name)
            self.__group = '%s/%s' % (group, name)

        self.check_same_thread = check_same_thread

    def add_arguments(self, parser):
        group = parser.add_argument_group(self.__group)
        group.add_argument(
            self.__arg, required=True,
            help='set database URL',
        )

    def check_arguments(self, parser, args):
        db_url = getattr(args, self.__attr)
        if not db_url.startswith('sqlite://'):
            parser.error('only support sqlite at the moment: %s' % db_url)

    def make(self, require):
        db_url = getattr(require.args, self.__attr)
        echo = logging.getLogger().isEnabledFor(LoggingComponent.TRACE)
        return garage.sql.sqlite.create_engine(
            db_url,
            check_same_thread=self.check_same_thread,
            echo=echo,
        )
