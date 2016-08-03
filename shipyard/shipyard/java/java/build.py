"""Install Java SE Development Kit 8."""

from pathlib import Path

from foreman import define_parameter, define_rule, decorate_rule
from shipyard import (
    copy_source,
    define_archive,
    ensure_file,
    execute,
    insert_path,
    rsync,
)


define_archive(
    uri='http://download.oracle.com/otn-pub/java/jdk/8u102-b14/jdk-8u102-linux-x64.tar.gz',
    filename='jdk-8u102-linux-x64.tar.gz',
    output='jdk1.8.0_102',
    derive_dst_path=lambda ps: ps['//base:build'] / 'host/java',
    wget_headers=['Cookie: oraclelicense=a'],
)


(define_parameter('java_root')
 .with_doc("""Location of Java build root.""")
 .with_type(Path)
 .with_derive(lambda ps: ps['//base:build'] / 'java')
)


(define_parameter('build_src')
 .with_doc("""Location of JDK.""")
 .with_type(Path)
 .with_derive(lambda ps: \
     ps['//base:build'] / 'host/java' / ps['archive_info'].output)
)


# NOTE: Do not allow multiple versions of JRE at the moment.
(define_parameter('java_output')
 .with_doc("""Location of tapeout'ed Java artifacts.""")
 .with_type(Path)
 .with_derive(lambda ps: ps['//base:build_rootfs'] / 'usr/local/lib/java')
)


@decorate_rule('//base:build',
               'download')
def install(parameters):
    """Install Java Development Kit."""
    jdk_bin = parameters['build_src'] / 'bin'
    ensure_file(jdk_bin / 'java')  # Sanity check.
    insert_path(jdk_bin)


@decorate_rule('//base:build',
               '//host/gradle:install',
               'install')
def build(parameters):
    """Prepare Java development environment."""

    # Copy source (because all Java projects are under one Gradle root
    # project and thus we don't copy Java projects individually).
    java_root = parameters['java_root']
    copy_source(parameters['//base:root'] / 'java', java_root)

    # Create gradle wrapper.
    execute(['gradle', 'wrapper'], cwd=java_root)


# NOTE: All Java package's `tapeout` rules should reverse depend on this
# rule (and `//base:tapeout`, too).
def tapeout(parameters):
    """Join point of all Java package's `tapeout` rule."""
    java_output = parameters['java_output']
    execute(['sudo', 'mkdir', '--parents', java_output])
    rsync([parameters['build_src'] / 'jre'], java_output, sudo=True)


(define_rule(tapeout.__name__)
 .with_doc(tapeout.__doc__)
 .with_build(tapeout)
 .depend('build')
 .reverse_depend('//base:tapeout')
)
