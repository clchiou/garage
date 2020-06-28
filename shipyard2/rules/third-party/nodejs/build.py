"""Install Node.js and npm."""

import foreman

from g1 import scripts

import shipyard2.rules.bases

shipyard2.rules.bases.define_archive(
    url='https://nodejs.org/dist/v14.4.0/node-v14.4.0-linux-x64.tar.xz',
    checksum='md5:d4edb4ad7f6670a0a680466d7de5e134',
)


@foreman.rule
@foreman.rule.depend('//bases:build')
@foreman.rule.depend('extract')
def build(parameters):
    scripts.export_path(
        'PATH',
        parameters['//bases:drydock'] / foreman.get_relpath() /
        parameters['archive'].output / 'bin',
    )
