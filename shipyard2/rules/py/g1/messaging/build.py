import logging
from pathlib import Path

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT

import shipyard2.rules.pythons

LOG = logging.getLogger(__name__)

shipyard2.rules.pythons.define_package(
    deps=[
        '//py/g1/bases:build',
    ],
    extras=[
        (
            'parts/clients',
            [
                '//py/g1/apps:build/asyncs',
            ],
        ),
        (
            'parts/pubsub',
            [
                '//py/g1/apps:build/asyncs',
                '//py/g1/asyncs/agents:build/parts',
            ],
        ),
        (
            'parts/servers',
            [
                '//py/g1/apps:build/asyncs',
                '//py/g1/asyncs/agents:build/parts',
            ],
        ),
        (
            'pubsub',
            [
                '//py/g1/asyncs/bases:build',
                '//py/g1/third-party/nng:build/asyncs',
            ],
        ),
        (
            'reqrep',
            [
                '//py/g1/third-party/nng:build/asyncs',
            ],
        ),
        ('wiredata.capnps', ['//py/g1/third-party/capnp:build']),
    ],
)


@foreman.rule('reqrep-client/build')
@foreman.rule.depend('//bases:build')
@foreman.rule.depend('//py/g1/apps:build/asyncs')
@foreman.rule.depend('//py/g1/asyncs/kernels:build')
@foreman.rule.depend('//py/g1/bases:build')
@foreman.rule.depend('//py/g1/messaging:build/reqrep')
@foreman.rule.depend('//py/g1/messaging:build/wiredata.capnps')
@foreman.rule.depend('//py/g1/third-party/capnp:build')
@foreman.rule.depend('//py/startup:build')
def reqrep_client_build(parameters):
    src_path = ASSERT.predicate(
        shipyard2.rules.pythons\
        .find_package(parameters, foreman.get_relpath()) /
        'scripts' /
        'reqrep-client',
        Path.is_file,
    )
    dst_path = Path('/usr/local/bin/reqrep-client')
    if dst_path.exists():
        LOG.info('skip: install reqrep-client')
        return
    LOG.info('install reqrep-client')
    with scripts.using_sudo():
        scripts.cp(src_path, dst_path)
