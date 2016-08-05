"""Set up Java environment."""

from pathlib import Path

from foreman import define_parameter, define_rule, decorate_rule
from shipyard import (
    copy_source,
    execute,
    rsync,
)


(define_parameter('build_src_root')
 .with_doc("""Location of Java build root.""")
 .with_type(Path)
 .with_derive(lambda ps: ps['//base:build'] / 'java')
)


JAVA_PATH = 'usr/local/lib/java'


# NOTE: Do not allow multiple versions of JRE at the moment.
(define_parameter('java_output')
 .with_doc("""Location of tapeout'ed Java artifacts.""")
 .with_type(Path)
 .with_derive(lambda ps: ps['//base:build_rootfs'] / JAVA_PATH)
)


(define_parameter('java_root')
 .with_doc("""Location of Java in the output image.""")
 .with_type(Path)
 .with_default(Path('/' + JAVA_PATH))
)


@decorate_rule('//base:build',
               '//host/gradle:install',
               '//host/java:install')
def build(parameters):
    """Prepare Java development environment."""

    # Copy source (because all Java projects are under one Gradle root
    # project and thus we don't copy Java projects individually).
    build_src_root = parameters['build_src_root']
    copy_source(parameters['//base:root'] / 'java', build_src_root)

    # Create gradle wrapper.
    if not (build_src_root / 'gradlew').exists():
        execute(['gradle', 'wrapper'], cwd=build_src_root)

    # Download and install gradle with the wrapper.
    execute(['./gradlew', ':help'], cwd=build_src_root)


# NOTE: All Java package's `tapeout` rules should reverse depend on this
# rule (and `//base:tapeout`, too).
def tapeout(parameters):
    """Join point of all Java package's `tapeout` rule."""
    java_output = parameters['java_output']
    execute(['sudo', 'mkdir', '--parents', java_output])
    rsync([parameters['//host/java:jdk'] / 'jre'], java_output, sudo=True)


(define_rule(tapeout.__name__)
 .with_doc(tapeout.__doc__)
 .with_build(tapeout)
 .depend('build')
 .reverse_depend('//base:tapeout')
)
