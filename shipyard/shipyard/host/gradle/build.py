"""Install Gradle build system."""

from pathlib import Path

from foreman import define_parameter, decorate_rule
from shipyard import (
    define_archive,
    ensure_file,
    insert_path,
)


define_archive(
    uri='https://services.gradle.org/distributions/gradle-2.14.1-bin.zip',
    filename='gradle-2.14.1-bin.zip',
    output='gradle-2.14.1',
    derive_dst_path=lambda ps: ps['//base:build'] / 'host/gradle',
)


(define_parameter('build_src')
 .with_type(Path)
 .with_derive(lambda ps: \
     ps['//base:build'] / 'host/gradle' / ps['archive_info'].output)
)


@decorate_rule('//base:build',
               '//java/java:install',
               'download')
def install(parameters):
    """Install Gradle build system."""
    gradle_bin = parameters['build_src'] / 'bin'
    ensure_file(gradle_bin / 'gradle')  # Sanity check.
    insert_path(gradle_bin)
