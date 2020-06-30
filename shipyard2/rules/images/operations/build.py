from pathlib import Path

import foreman

from g1 import scripts

import shipyard2.rules.images

OPS_DB_PATH = Path('/srv/operations/database')

shipyard2.rules.images.define_image(
    name='ops-db',
    rules=[
        '//py/g1/operations/databases/servers:build/apps',
        'ops-db/setup',
    ],
)


@foreman.rule('ops-db/setup')
@foreman.rule.depend('//bases:build')
def ops_db_setup(parameters):
    del parameters  # Unused.
    with scripts.using_sudo():
        scripts.mkdir(OPS_DB_PATH)
        scripts.chown('nobody', None, OPS_DB_PATH)
