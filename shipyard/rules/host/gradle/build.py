from foreman import get_relpath, rule

from garage import scripts

from templates import common


common.define_archive(
    uri='https://services.gradle.org/distributions/gradle-4.7-bin.zip',
    filename='gradle-4.7-bin.zip',
    output='gradle-4.7',
    checksum='md5-3e5af867778cd0a8e00e62257f426e09',
)


@rule
@rule.depend('//base:build')
@rule.depend('//host/java:install')
@rule.depend('download')
def install(parameters):
    """Install Gradle build system."""
    bin_dir = (parameters['//base:drydock'] / get_relpath() /
               parameters['archive_info'].output / 'bin')
    scripts.ensure_file(bin_dir / 'gradle')  # Sanity check
    scripts.insert_path(bin_dir)
