"""Install Gradle build system."""

import logging
import os
from collections import namedtuple
from pathlib import Path

from foreman import define_parameter, decorate_rule
from shipyard import (
    ensure_directory,
    execute,
    wget,
)


LOG = logging.getLogger(__name__)


ZipInfo = namedtuple('ZipInfo', 'uri filename output')
(define_parameter('zip')
 .with_doc("""Gradle zip archive.""")
 .with_type(ZipInfo)
 .with_parse(lambda info: ZipInfo(*info.split(',')))
 .with_default(ZipInfo(
     uri='https://services.gradle.org/distributions/gradle-2.14.1-bin.zip',
     filename='gradle-2.14.1-bin.zip',
     output='gradle-2.14.1',
 ))
)


(define_parameter('build_src')
 .with_type(Path)
 .with_derive(lambda ps: \
     ps['//base:build'] / 'host/gradle' / ps['zip'].output)
)


@decorate_rule('//base:build',
               '//java/java:install')
def install(parameters):
    """Install Gradle build system."""

    build_src = parameters['build_src']
    ensure_directory(build_src.parent)
    zip_path = build_src.parent / parameters['zip'].filename
    if not zip_path.exists():
        LOG.info('download zip archive')
        wget(parameters['zip'].uri, zip_path)
    if not build_src.exists():
        LOG.info('extract zip archive')
        execute(['unzip', parameters['zip'].filename], cwd=build_src.parent)

    assert build_src.exists()
    gradle_bin = build_src / 'bin'
    path = os.environ.get('PATH')
    path = '%s:%s' % (gradle_bin, path) if path else str(gradle_bin)
    os.environ['PATH'] = path
