"""Install Java SE Development Kit 8."""

import logging
from collections import namedtuple
from pathlib import Path

from foreman import define_parameter, define_rule, decorate_rule
from shipyard import (
    ensure_directory,
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


(define_parameter('build_src')
 .with_type(Path)
 .with_derive(lambda ps: \
     ps['//base:build'] / 'java/java' / ps['tarball'].output)
)


@decorate_rule('//base:build')
def build(parameters):
    """Install JDK."""
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


# NOTE: All Java package's `tapeout` rules should reverse depend on this
# rule (and `//base:tapeout`, too).
def tapeout(parameters):
    """Join point of all Java package's `tapeout` rule."""
    LOG.info('copy jre')
    # NOTE: Do not allow multiple versions of JRE in /opt for now.
    rsync([parameters['build_src'] / 'jre'],
          (parameters['//base:build_rootfs'] / 'opt'))


(define_rule(tapeout.__name__)
 .with_doc(tapeout.__doc__)
 .with_build(tapeout)
 .depend('build')
 .reverse_depend('//base:tapeout')
)
