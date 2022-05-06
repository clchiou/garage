from pathlib import Path

import foreman

from g1 import scripts

import shipyard2.rules.images

OPS_DB_PATH = Path('/srv/operations/database/v1')

shipyard2.rules.images.define_image(
    name='database',
    rules=[
        '//python/g1/operations/databases/servers:build/apps',
        'database/setup',
    ],
)


@foreman.rule('database/setup')
@foreman.rule.depend('//bases:build')
def database_setup(parameters):
    del parameters  # Unused.
    with scripts.using_sudo():
        scripts.mkdir(OPS_DB_PATH)


shipyard2.rules.images.define_xar_image(
    name='ops-db-client',
    rules=[
        '//python/g1/operations/databases/clients:ops-db-client/build',
        'ops-db-client/setup',
    ],
)


@foreman.rule('ops-db-client/setup')
@foreman.rule.depend('//bases:build')
def ops_db_client_setup(parameters):
    del parameters  # Unused.
    shipyard2.rules.images.generate_exec_wrapper(
        'usr/local/bin/ops-db-client',
        'usr/local/bin/run-ops-db-client',
    )
