"""Helper for initializing SQLAlchemy Engine object."""

__all__ = [
    'add_db_uri_arg',
    'check_db_uri',
    'make_engine',
]

import logging

import garage.sql
import garage.sql.sqlite

from garage.startups.logging import LoggingComponent


def add_db_uri_arg(parser, db_uri_arg):
    parser.add_argument(
        db_uri_arg, required=True,
        help="""set database engine URI""")


def check_db_uri(parser, args, db_uri_arg, db_uri_name):
    db_uri = getattr(args, db_uri_name)
    if not db_uri.startswith('sqlite'):
        parser.error('only support sqlite in "%s" at the moment' % db_uri_arg)


def make_engine(args, db_uri_name):
    db_uri = getattr(args, db_uri_name)
    echo = logging.getLogger().isEnabledFor(LoggingComponent.TRACE)
    return garage.sql.sqlite.create_engine(db_uri, echo=echo)
