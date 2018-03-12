import functools

import curio

from garage import asyncs
from garage import parameters
from garage import parts
from garage.asyncs import servers


PARTS = parts.Parts(servers.__name__)
PARTS.graceful_exit = parts.AUTO
PARTS.server = parts.AUTO
PARTS.run_servers = parts.AUTO


PARAMS = parameters.define_namespace(
    servers.__name__, 'async servers')
PARAMS.grace_period = parameters.create(
    5, unit='second', doc='grace period for shutting down servers')


@parts.define_maker
def make_graceful_exit() -> PARTS.graceful_exit:
    return asyncs.Event()


@parts.define_maker
def make_run_servers(
        graceful_exit: PARTS.graceful_exit,
        server_coros: [PARTS.server],
    ) -> PARTS.run_servers:
    return functools.partial(
        servers.serve,
        graceful_exit=graceful_exit,
        grace_period=PARAMS.grace_period.get(),
        server_coros=server_coros,
    )


#
# A stock main function.
#
# NOTE: Do not decorate it with `@apps`, which creates an apps.App
# object, because it might be shared in multiple places, and if they all
# decorate it further, they will be modifying the same apps.App object.
def main(_, run_servers: PARTS.run_servers):
    return 0 if curio.run(run_servers()) else 1
