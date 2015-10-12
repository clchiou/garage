"""Initialize sqlalchemy."""

__all__ = [
    'SqlComponent',
]

import logging

from sqlalchemy import MetaData

from garage import components
from garage import sql

import garage.sql.sqlite # as sql.sqlite

from garage.startups.logging import LoggingComponent


class SqlComponent(components.Component):

    require = components.ARGS

    provide = components.make_provide(__name__, 'engine', 'metadata')

    def add_arguments(self, parser):
        group = parser.add_argument_group(sql.__name__)
        group.add_argument(
            '--db-uri', required=True,
            help="""set database engine URI""")

    def check_arguments(self, parser, args):
        if not args.db_uri.startswith('sqlite'):
            parser.error('only support sqlite in "--db-uri" at the moment')

    def make(self, require):
        echo = logging.getLogger().isEnabledFor(LoggingComponent.TRACE)
        return (
            sql.sqlite.create_engine(require.args.db_uri, echo=echo),
            MetaData(),
        )
