__all__ = [
    'create_engine',
]

import re

import sqlalchemy

from g1.bases.assertions import ASSERT

DB_URL_PATTERN = re.compile(r'postgresql(\+.*)?://')


def create_engine(db_url):
    ASSERT(
        DB_URL_PATTERN.match(db_url), 'expect postgresql URL, not {!r}', db_url
    )
    return sqlalchemy.create_engine(db_url)
