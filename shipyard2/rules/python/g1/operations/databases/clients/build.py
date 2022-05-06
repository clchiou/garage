import logging
from pathlib import Path

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT

import shipyard2.rules.pythons

LOG = logging.getLogger(__name__)

shipyard2.rules.pythons.define_package(
    deps=[
        '//python/g1/messaging:build/reqrep',
        '//python/g1/operations/databases/bases:build/capnps',
    ],
    extras=[
        (
            'parts',
            [
                '//python/g1/apps:build',
                '//python/g1/bases:build',
                '//python/g1/messaging:build/parts/clients',
            ],
        ),
    ],
)


@foreman.rule('ops-db-client/build')
@foreman.rule.depend('//bases:build')
@foreman.rule.depend('//python/g1/apps:build/asyncs')
@foreman.rule.depend('//python/g1/asyncs/kernels:build')
@foreman.rule.depend('//python/g1/bases:build')
@foreman.rule.depend('//python/g1/operations/databases/bases:build')
@foreman.rule.depend('//python/g1/operations/databases/clients:build/parts')
@foreman.rule.depend('//python/startup:build')
def ops_db_client_build(parameters):
    src_path = ASSERT.predicate(
        shipyard2.rules.pythons\
        .find_package(parameters, foreman.get_relpath()) /
        'scripts' /
        'ops-db-client',
        Path.is_file,
    )
    dst_path = Path('/usr/local/bin/ops-db-client')
    if dst_path.exists():
        LOG.info('skip: install ops-db-client')
        return
    LOG.info('install ops-db-client')
    with scripts.using_sudo():
        scripts.cp(src_path, dst_path)
