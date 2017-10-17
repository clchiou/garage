from foreman import define_parameter, get_relpath, rule

from garage import scripts

from templates import common


common.define_archive(
    uri='http://download.oracle.com/otn-pub/java/jdk/8u152-b16/aa0333dd3019491ca4f6ddbe78cdb6d0/jdk-8u152-linux-x64.tar.gz',
    filename='jdk-8u152-linux-x64.tar.gz',
    output='jdk1.8.0_152',
    checksum='md5-20dddd28ced3179685a5f58d3fcbecd8',
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
