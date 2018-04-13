"""Build (standard) Filebeat image."""

from foreman import get_relpath, rule

from garage import scripts

from templates import common, pods


common.define_archive(
    uri='https://artifacts.elastic.co/downloads/beats/filebeat/filebeat-5.6.3-linux-x86_64.tar.gz',
    filename='filebeat-5.6.3-linux-x86_64.tar.gz',
    output='filebeat-5.6.3-linux-x86_64',
    checksum='md5-07153569880e274827ead38aa9a40289',
)


@rule
@rule.depend('//base:build')
@rule.depend('download')
def build(_):
    pass  # Nothing here for now.


@rule
@rule.depend('build')
@rule.reverse_depend('//base:tapeout')
def tapeout(parameters):
    with scripts.using_sudo():
        input_path = (
            parameters['//base:drydock'] / get_relpath() /
            parameters['archive_info'].output
        )

        output = parameters['//base:drydock/rootfs'] / 'opt/filebeat'
        scripts.mkdir(output)

        # Appending '/' to src is an rsync trick.
        scripts.rsync(['%s/' % input_path], output)

        # `config`, `data`, and `logs` are provided by application pod.
        scripts.mkdir(output / 'config')
        scripts.mkdir(output / 'data')
        scripts.mkdir(output / 'logs')

        # Filebeat requires most of the files owned by the same user.
        scripts.execute(['chown', '--recursive', 'root:root', output])


@rule
@rule.depend('//base:tapeout')
def trim(parameters):
    rootfs = parameters['//base:drydock/rootfs']
    with scripts.using_sudo():
        scripts.rm(rootfs / 'lib', recursive=True)
        scripts.rm(rootfs / 'usr', recursive=True)


@pods.app_specifier
def filebeat_app(_):
    return pods.App(
        name='filebeat',
        exec=[
            'filebeat',
            '-e',
            '-c', 'config/filebeat.yml',
        ],
        # Filebeat needs read permission on log files.
        user='root', group='root',
        working_directory='/opt/filebeat',
        # Filebeat requires most of the files owned by the same user.
        volumes=[
            pods.Volume(
                name='etc-hosts-volume',
                path='/etc/hosts',
                host_path='/etc/hosts',
            ),
            pods.Volume(
                name='data-volume',
                path='/opt/filebeat/data',
                read_only=False,
                user='root', group='root',
            ),
            pods.Volume(
                name='logs-volume',
                path='/opt/filebeat/logs',
                read_only=False,
                user='root', group='root',
            ),
            pods.Volume(
                name='host-logs-volume',
                path='/var/log',
                host_path='/var/log',
            ),
        ],
    )
