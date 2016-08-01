"""Template of DbEngineComponent."""

__all__ = [
    'make_db_engine_component',
]

import logging

import garage.sql.sqlite
from garage import components
from garage.startups.logging import LoggingComponent


def make_db_engine_component(
        *,
        package_name,
        argument_group,
        argument_prefix):

    DB_URL = '%s_db_url' % argument_prefix.replace('-', '_')

    class DbEngineComponent(components.Component):

        require = components.ARGS

        provide = components.make_fqname_tuple(package_name, 'engine')

        def add_arguments(self, parser):
            group = parser.add_argument_group(argument_group)
            group.add_argument(
                '--%s-db-url' % argument_prefix, required=True,
                help="""set database URL""")

        def check_arguments(self, parser, args):
            db_url = getattr(args, DB_URL)
            if not db_url.startswith('sqlite'):
                parser.error('only support sqlite at the moment: %s' % db_url)

        def make(self, require):
            db_url = getattr(require.args, DB_URL)
            echo = logging.getLogger().isEnabledFor(LoggingComponent.TRACE)
            return garage.sql.sqlite.create_engine(db_url, echo=echo)

    # Hack for manipulating call order.
    DbEngineComponent.add_arguments.__module__ = package_name
    DbEngineComponent.check_arguments.__module__ = package_name

    return DbEngineComponent
