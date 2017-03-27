from foreman import define_parameter, get_relpath, rule

from garage import scripts

from templates import common


common.define_archive(
    uri='http://download.oracle.com/otn-pub/java/jdk/8u121-b13/e9e7ea248e2c4826b92b3f075a80e441/jdk-8u121-linux-x64.tar.gz',
    filename='jdk-8u121-linux-x64.tar.gz',
    output='jdk1.8.0_121',
    checksum='md5-91972fb4e753f1b6674c2b952d974320',
    wget_headers=['Cookie: oraclelicense=accept-securebackup-cookie'],
)


# //java/base will use this
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
