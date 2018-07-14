from foreman import get_relpath, rule

from garage import scripts

from templates import common


common.define_archive(
    uri='https://github.com/appc/docker2aci/releases/download/v0.17.2/docker2aci-v0.17.2.tar.gz',
    filename='docker2aci-v0.17.2.tar.gz',
    output='docker2aci-v0.17.2',
    checksum='md5-01ee7d32ae471605d77ef15c2aa934c5',
)


@rule
@rule.depend('//base:build')
@rule.depend('download')
def install(parameters):
    bin_dir = (
        parameters['//base:drydock'] /
        get_relpath() /
        parameters['archive_info'].output
    )
    scripts.ensure_file(bin_dir / 'docker2aci')  # Sanity check
    scripts.insert_path(bin_dir)
