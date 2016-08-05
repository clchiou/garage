"""Install Java SE Development Kit."""

from pathlib import Path

from foreman import define_parameter, decorate_rule
from shipyard import (
    define_archive,
    ensure_file,
    insert_path,
)


define_archive(
    uri='http://download.oracle.com/otn-pub/java/jdk/8u102-b14/jdk-8u102-linux-x64.tar.gz',
    filename='jdk-8u102-linux-x64.tar.gz',
    output='jdk1.8.0_102',
    derive_dst_path=lambda ps: ps['//base:build'] / 'host/java',
    wget_headers=['Cookie: oraclelicense=a'],
)


(define_parameter('jdk')
 .with_doc("""Location of JDK.""")
 .with_type(Path)
 .with_derive(lambda ps: \
     ps['//base:build'] / 'host/java' / ps['archive_info'].output)
)


@decorate_rule('//base:build',
               'download')
def install(parameters):
    """Install Java Development Kit."""
    jdk_bin = parameters['jdk'] / 'bin'
    ensure_file(jdk_bin / 'java')  # Sanity check.
    insert_path(jdk_bin)
