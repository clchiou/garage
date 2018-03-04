import logging
import typing

import garage.apps
import garage.sql.sqlite
from garage import parameters
from garage import parts
from garage.assertions import ASSERT


def define_parts(module_name):
    return parts.PartList(module_name, [
        ('engine', parts.AUTO),
    ])


def define_params(*, check_same_thread=False, pragmas=()):
    params = parameters.define_namespace('create SQLAlchemy Engine object')
    params.db_url = parameters.define(
        'sqlite:///:memory:',
        'set database URL',
    )
    params.check_same_thread = parameters.define(
        check_same_thread,
        'check database connection created and used in the same thread',
    )
    params.pragmas = parameters.define(
        pragmas,
        type=typing.List[typing.Tuple[str, str]],
        doc='add pragma setting(s) to database',
    )
    return params


def define_maker(part_list, params):

    def make_engine() -> part_list.engine:
        db_url = params.db_url.get()
        ASSERT(
            db_url.startswith('sqlite://'),
            'expect only sqlite at the moment: %s', db_url,
        )
        echo = logging.getLogger().isEnabledFor(garage.apps.TRACE)
        return garage.sql.sqlite.create_engine(
            db_url,
            check_same_thread=params.check_same_thread.get(),
            echo=echo,
            pragmas=params.pragmas.get(),
        )

    return make_engine