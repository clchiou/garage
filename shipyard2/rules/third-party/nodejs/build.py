"""Install Node.js and npm."""

import foreman

from g1 import scripts

import shipyard2.rules.bases

shipyard2.rules.bases.define_archive(
    url='https://nodejs.org/dist/v18.3.0/node-v18.3.0-linux-x64.tar.xz',
    checksum=
    'sha256:e374f0e7726fd36e33846f186c3d17e41f7d62758e9af72c379b6583e73ffd48',
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
