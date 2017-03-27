from foreman import get_relpath, rule

from garage import scripts

from templates import common


common.define_archive(
    uri='https://services.gradle.org/distributions/gradle-3.4.1-bin.zip',
    filename='gradle-3.4.1-bin.zip',
    output='gradle-3.4.1',
    checksum='md5-ccfa2f8bbfd572dea495e17b0079ec03',
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
