"""Initialize sqlalchemy."""

__all__ = [
    'ENGINE',
    'METADATA',
    'init',
]

import logging

from sqlalchemy import MetaData

from startup import startup

import garage.sqlalchemy
from garage.functools import run_once
from garage.sqlalchemy import sqlite

import garage.startups.logging
from garage.startups import ARGS, PARSE, PARSER
from garage.startups import components


ENGINE = __name__ + ':engine'
METADATA = __name__ + ':metadata'


def add_arguments(parser: PARSER) -> PARSE:
    group = parser.add_argument_group(garage.sqlalchemy.__name__)
    group.add_argument(
        '--db-uri', required=True,
        help="""set database engine URI""")


def check_db_uri(parser: PARSER, args: ARGS):
    if not args.db_uri.startswith('sqlite'):
        parser.error('only support sqlite in "--db-uri" at the moment')


def make_engine(args: ARGS) -> ENGINE:
    echo = logging.getLogger().isEnabledFor(garage.startups.logging.TRACE)
    return sqlite.create_engine(args.db_uri, echo=echo)


@run_once
def init():
    startup(add_arguments)
    startup(check_db_uri)
    components.startup(make_engine)
    components.startup.with_annotations({'return': METADATA})(MetaData)
