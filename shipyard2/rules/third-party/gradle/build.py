"""Install Gradle."""

import foreman

from g1 import scripts

import shipyard2.rules.bases

shipyard2.rules.bases.define_archive(
    url='https://services.gradle.org/distributions/gradle-7.2-bin.zip',
    checksum=
    'sha256:f581709a9c35e9cb92e16f585d2c4bc99b2b1a5f85d2badbd3dc6bff59e1e6dd',
    output='gradle-7.2',
)


@foreman.rule
@foreman.rule.depend('//bases:build')
@foreman.rule.depend('//third-party/openjdk:build')
@foreman.rule.depend('extract')
def build(parameters):
    scripts.export_path(
        'PATH',
        parameters['//bases:drydock'] / foreman.get_relpath() /
        parameters['archive'].output / 'bin',
    )
