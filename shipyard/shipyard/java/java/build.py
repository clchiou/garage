"""Install Java SE Development Kit 8."""

import logging
import os
from collections import namedtuple
from pathlib import Path

from foreman import define_parameter, define_rule, decorate_rule
from shipyard import (
    copy_source,
    ensure_directory,
    ensure_file,
    execute,
    rsync,
    tar_extract,
    wget,
)


LOG = logging.getLogger(__name__)


TarballInfo = namedtuple('TarballInfo', 'uri filename output')
(define_parameter('tarball')
 .with_doc("""JDK tarball.""")
 .with_type(TarballInfo)
 .with_parse(lambda info: TarballInfo(*info.split(',')))
 .with_default(TarballInfo(
     uri='http://download.oracle.com/otn-pub/java/jdk/8u102-b14/jdk-8u102-linux-x64.tar.gz',
     filename='jdk-8u102-linux-x64.tar.gz',
     output='jdk1.8.0_102',
 ))
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
     ps['//base:build'] / 'host/java' / ps['tarball'].output)
)


# NOTE: Do not allow multiple versions of JRE at the moment.
(define_parameter('java_output')
 .with_doc("""Location of tapeout'ed Java artifacts.""")
 .with_type(Path)
 .with_derive(lambda ps: ps['//base:build_rootfs'] / 'usr/local/lib/java')
)


@decorate_rule('//base:build')
def install(parameters):
    """Install Java Development Kit"""

    # Download JDK.
    build_src = parameters['build_src']
    ensure_directory(build_src.parent)
    tarball_path = build_src.parent / parameters['tarball'].filename
    if not tarball_path.exists():
        LOG.info('download tarball')
        wget(parameters['tarball'].uri, tarball_path,
             headers=['Cookie: oraclelicense=a'])
    if not build_src.exists():
        LOG.info('extract tarball')
        tar_extract(tarball_path, build_src.parent)

    # Add jdk/bin to PATH.
    jdk_bin = build_src / 'bin'
    ensure_file(jdk_bin / 'java')
    path = os.environ.get('PATH')
    path = '%s:%s' % (jdk_bin, path) if path else str(jdk_bin)
    os.environ['PATH'] = path


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
    LOG.info('copy Java runtime environment')
    java_output = parameters['java_output']
    execute(['sudo', 'mkdir', '--parents', java_output])
    rsync([parameters['build_src'] / 'jre'], java_output, sudo=True)


(define_rule(tapeout.__name__)
 .with_doc(tapeout.__doc__)
 .with_build(tapeout)
 .depend('build')
 .reverse_depend('//base:tapeout')
)
