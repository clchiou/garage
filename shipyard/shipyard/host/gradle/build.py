"""Install Gradle build system."""

from foreman import decorate_rule
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


@decorate_rule('//base:build',
               '//host/java:install',
               'download')
def install(parameters):
    """Install Gradle build system."""
    gradle_bin = (
        parameters['archive_destination'] /
        parameters['archive_info'].output /
        'bin'
    )
    ensure_file(gradle_bin / 'gradle')  # Sanity check.
    insert_path(gradle_bin)
