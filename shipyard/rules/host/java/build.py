from foreman import define_parameter, get_relpath, rule

from garage import scripts

from templates import common


common.define_archive(
    uri='http://download.oracle.com/otn-pub/java/jdk/8u144-b01/090f390dda5b47b9b721c7dfaa008135/jdk-8u144-linux-x64.tar.gz',
    filename='jdk-8u144-linux-x64.tar.gz',
    output='jdk1.8.0_144',
    checksum='md5-2d59a3add1f213cd249a67684d4aeb83',
    wget_headers=['Cookie: oraclelicense=accept-securebackup-cookie'],
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
