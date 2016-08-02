"""Templates for building Java packages."""

__all__ = [
    'define_package',
]

from foreman import define_rule

from . import (
    ensure_file,
    execute,
    rsync,
)


def define_package(
        *,
        package_name,
        jar_file_name=None,
        build_rule_deps=(),
        tapeout_rule_deps=()):

    build_task = ':%s:build' % package_name.replace('.', ':')

    def build(parameters):
        execute(['./gradlew', build_task],
                cwd=parameters['//java/java:java_root'])

    build_rule = (
        define_rule('build')
        .with_doc("""Build Java package.""")
        .with_build(build)
        .depend('//base:build')
        .depend('//java/java:build')
    )
    for rule in build_rule_deps:
        build_rule.depend(rule)

    if jar_file_name is None:
        jar_file_name = package_name[package_name.rfind('.') + 1:] + '.jar'

    package_path = package_name.replace('.', '/')

    def tapeout(parameters):
        jar_path = (
            parameters['//java/java:java_root'] /
            package_path / 'build/libs' / jar_file_name
        )
        ensure_file(jar_path)
        java_output = parameters['//java/java:java_output']
        execute(['sudo', 'mkdir', '--parents', java_output])
        rsync([jar_path], java_output, sudo=True)

    tapeout_rule = (
        define_rule('tapeout')
        .with_doc("""Copy JAR file.""")
        .with_build(tapeout)
        .depend('build')
        .reverse_depend('//base:tapeout')
        .reverse_depend('//java/java:tapeout')
    )
    for rule in tapeout_rule_deps:
        tapeout_rule.depend(rule)
