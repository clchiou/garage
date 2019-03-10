__all__ = [
    'create_engine',
]

import re

import sqlalchemy

from g1.bases.assertions import ASSERT

PATTERN_DB_URL = re.compile(r'postgresql(\+.*)?://')


def create_engine(db_url):
    ASSERT(
        PATTERN_DB_URL.match(db_url), 'expect postgresql URL, not {!r}', db_url
    )
    return sqlalchemy.create_engine(db_url)
