from foreman import define_parameter, get_relpath, rule

from garage import scripts

from templates import common


# Oracle makes programmatically downloading JDK very hard; let's use a
# local copy instead.
common.define_local_archive(
    path='jdk/jdk-8u172-linux-x64.tar.gz',
    output='jdk1.8.0_172',
    checksum='md5-eda2945e8c02b84adbf78f46c37b71c1',
)


# //java/java will use this.
(define_parameter.path_typed('jdk')
 .with_doc('Path to JDK.')
 .with_derive(
     lambda ps:
     ps['//base:drydock'] / get_relpath() / ps['archive_info'].output))


@rule
@rule.depend('//base:build')
@rule.depend('download')
def install(parameters):
    """Install Java SE Development Kit."""
    bin_dir = parameters['jdk'] / 'bin'
    scripts.ensure_file(bin_dir / 'java')  # Sanity check
    scripts.insert_path(bin_dir)
