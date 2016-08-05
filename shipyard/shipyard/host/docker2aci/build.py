"""Install docker2aci."""

from foreman import decorate_rule
from shipyard import (
    define_archive,
    ensure_file,
    insert_path,
)


define_archive(
    uri='https://github.com/appc/docker2aci/releases/download/v0.12.3/docker2aci-v0.12.3.tar.gz',
    filename='docker2aci-v0.12.3.tar.gz',
    output='docker2aci-v0.12.3',
    derive_dst_path=lambda ps: ps['//base:build'] / 'host/docker2aci',
)


@decorate_rule('//base:build',
               'download')
def install(parameters):
    """Install docker2aci."""
    docker2aci_bin = (
        parameters['archive_destination'] /
        parameters['archive_info'].output
    )
    ensure_file(docker2aci_bin / 'docker2aci')  # Sanity check.
    insert_path(docker2aci_bin)
