from foreman import get_relpath, rule

from garage import scripts

from templates.common import define_distro_packages


GRAFANA_DEB = 'grafana_5.1.4_amd64.deb'
GRAFANA_DEB_URI = 'https://s3-us-west-2.amazonaws.com/grafana-releases/release/grafana_5.1.4_amd64.deb'
GRAFANA_DEB_CHECKSUM = 'sha256-bbec4cf6112c4c2654b679ae808aaad3b3e4ba39818a6d01f5f19e78946b734e'


define_distro_packages([
    'adduser',
    'libfontconfig',
])


@rule
@rule.depend('//base:build')
@rule.depend('install_packages')
def build(parameters):
    drydock_src = parameters['//base:drydock'] / get_relpath()
    scripts.mkdir(drydock_src)
    with scripts.directory(drydock_src):
        deb_path = drydock_src / GRAFANA_DEB
        if not deb_path.exists():
            scripts.wget(GRAFANA_DEB_URI, deb_path)
            scripts.ensure_checksum(deb_path, GRAFANA_DEB_CHECKSUM)
        with scripts.using_sudo():
            scripts.execute(['dpkg', '--install', deb_path])


@rule
@rule.depend('build')
@rule.reverse_depend('//base:tapeout')
def tapeout(parameters):
    with scripts.using_sudo():
        rootfs = parameters['//base:drydock/rootfs']
        scripts.rsync(
            [
                '/usr/sbin/grafana-server',
                '/usr/share/grafana',
            ],
            rootfs,
            relative=True,
        )


@rule
@rule.depend('//base:tapeout')
def trim_usr(parameters):
    rootfs = parameters['//base:drydock/rootfs']
    with scripts.using_sudo():
        scripts.rm(rootfs / 'usr/lib', recursive=True)
        scripts.rm(rootfs / 'usr/local/lib', recursive=True)
