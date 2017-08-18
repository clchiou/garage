"""Set up Java runtime environment."""

from pathlib import Path

from foreman import define_parameter, rule

from garage import scripts

from templates import common


(define_parameter.path_typed('jre')
 .with_doc('Path to JRE.')
 .with_default(Path('/usr/local/lib/java/jre')))


(define_parameter.path_typed('packages')
 .with_doc('Path to directory of Java packages')
 .with_default(Path('/usr/local/lib/java/packages')))


# Copy source (because all Java projects are under one Gradle root
# project and thus we don't copy Java projects individually).
common.define_copy_src(src_relpath='java', dst_relpath='java')


@rule
@rule.depend('//base:build')
@rule.depend('//host/gradle:install')
@rule.depend('//host/java:install')
@rule.depend('copy_src')
def build(parameters):
    """Prepare Java development environment."""
    # Prepare build environment.
    drydock_src = parameters['//base:drydock'] / 'java'
    if not (drydock_src / 'gradlew').exists():
        with scripts.directory(drydock_src):
            # Create gradle wrapper.
            scripts.execute(['gradle', 'wrapper'])
            # Download the gradle of version pinned in build.gradle.
            scripts.execute(['./gradlew', '--version'])
    # Copy JRE to /usr/local/lib.
    with scripts.using_sudo():
        jre = parameters['jre']
        scripts.mkdir(jre)
        # Appending '/' to src is an rsync trick.
        src = parameters['//host/java:jdk'] / 'jre'
        scripts.rsync(['%s/' % src], jre)


@rule
@rule.depend('build')
@rule.reverse_depend('//base:tapeout')
def tapeout(parameters):
    """Tape-out Java.

    NOTE: All Java package's `tapeout` rules should reverse depend on
    this rule.
    """
    with scripts.using_sudo():
        rootfs = parameters['//base:drydock/rootfs']
        jre = parameters['jre']
        packages = parameters['packages']
        scripts.rsync([jre, packages], rootfs, relative=True)
