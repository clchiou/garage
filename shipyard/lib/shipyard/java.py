"""Templates for building Java packages."""

__all__ = [
    # Helpers
    'make_manifest',
    # Templates
    'define_package',
]

from foreman import define_rule

from . import (
    ensure_file,
    execute,
    rsync,
)


def make_manifest(parameters, manifest):
    """Make base Java image manifest."""
    assert 'app' not in manifest
    manifest['app'] = {
        'exec': [str(parameters['//java/java:java_root'] / 'jre/bin/java')],
        'user': 'nobody',
        'group': 'nogroup',
        'workingDirectory': '/',
    }
    return manifest


def define_package(
        *,
        package_name,
        jar_file_name=None,
        build_rule_deps=(),
        tapeout_rule_deps=()):

    build_task = ':%s:build' % package_name.replace('.', ':')

    def build(parameters):
        execute(['./gradlew', build_task],
                cwd=parameters['//java/java:build_src_root'])

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
            parameters['//java/java:build_src_root'] /
            package_path / 'build/libs' / jar_file_name
        )
        ensure_file(jar_path)
        java_libs = parameters['//java/java:java_output'] / 'libs'
        execute(['sudo', 'mkdir', '--parents', java_libs])
        rsync([jar_path], java_libs, sudo=True)

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
