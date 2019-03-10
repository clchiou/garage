import collections.abc
import functools
import logging

from g1.apps import labels
from g1.apps import loggers
from g1.apps import parameters
from g1.apps import utils
from g1.bases.assertions import ASSERT

from . import postgresql
from . import sqlite

DATABASE_LABEL_NAMES = (
    'create_engine_params',
    'create_engine',
)


def define_create_engine(module_path=None, **kwargs):
    """Define a database engine under ``module_path``."""
    module_path = module_path or __package__
    module_labels = labels.make_labels(module_path, *DATABASE_LABEL_NAMES)
    setup_create_engine(
        module_labels,
        parameters.define(module_path, make_create_engine_params(**kwargs)),
    )
    return module_labels


def setup_create_engine(module_labels, module_params):
    utils.depend_parameter_for(
        module_labels.create_engine_params, module_params
    )
    utils.define_maker(
        make_create_engine,
        {
            'params': module_labels.create_engine_params,
            'return': module_labels.create_engine,
        },
    )


def make_create_engine_params(db_url='', dialect='', **kwargs):

    dialect = get_dialect(db_url, dialect)

    if dialect == 'postgresql':
        params = parameters.Namespace(
            'make PostgreSQL database engine',
            db_url=parameters.Parameter(db_url),
            dialect=parameters.Parameter(dialect),
        )

    elif dialect == 'sqlite':
        params = parameters.Namespace(
            'make SQLite database engine',
            db_url=parameters.Parameter(db_url),
            dialect=parameters.Parameter(dialect),
            check_same_thread=parameters.Parameter(
                kwargs.get('check_same_thread', True)
            ),
            trace=parameters.Parameter(
                kwargs.get('trace'), type=(bool, type(None))
            ),
            pragmas=parameters.Parameter(
                kwargs.get('pragmas', ()), type=collections.abc.Iterable
            ),
        )

    else:
        ASSERT.unreachable('unsupported dialect: {}', dialect)

    return params


def make_create_engine(params):

    kwargs = {
        'db_url': params.db_url.get(),
    }

    dialect = params.dialect.get()

    if dialect == 'postgresql':
        create_engine = postgresql.create_engine

    elif dialect == 'sqlite':
        create_engine = sqlite.create_engine
        trace = params.trace.get()
        if trace is None:
            trace = logging.getLogger().isEnabledFor(loggers.TRACE)
        kwargs['check_same_thread'] = params.check_same_thread.get()
        kwargs['trace'] = trace
        kwargs['pragmas'] = params.pragmas.get()

    else:
        ASSERT.unreachable('unsupported dialect: {}', dialect)

    return functools.partial(create_engine, **kwargs)


def get_dialect(db_url, dialect):
    for name in ('postgresql', 'sqlite'):
        if db_url.startswith(name) or dialect == name:
            break
    else:
        ASSERT.unreachable('unsupported dialect: {!r}', db_url or dialect)
    return name
