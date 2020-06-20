"""Install Gradle."""

import foreman

from g1 import scripts

import shipyard2.rules.bases

shipyard2.rules.bases.define_archive(
    url='https://services.gradle.org/distributions/gradle-6.5-bin.zip',
    checksum='md5:32994c65fe691784c9e4a04ce1a9cfb1',
    output='gradle-6.5',
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
