"""Install Node.js and npm."""

import foreman

from g1 import scripts

import shipyard2.rules.bases

shipyard2.rules.bases.define_archive(
    url='https://nodejs.org/dist/v14.18.0/node-v14.18.0-linux-x64.tar.xz',
    checksum=
    'sha256:5c0bc18b19fd09ff80beb16772e69cb033ee4992a4ccd35bd884fd8f02e6d1ec',
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
