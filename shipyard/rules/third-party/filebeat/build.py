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
def build(parameters):
    pass  # Nothing here for now.


@rule
@rule.depend('build')
@rule.reverse_depend('//base:tapeout')
def tapeout(parameters):
    with scripts.using_sudo():
        input = (
            parameters['//base:drydock'] / get_relpath() /
            parameters['archive_info'].output
        )

        output = parameters['//base:drydock/rootfs'] / 'opt/filebeat'
        scripts.mkdir(output)

        # Appending '/' to src is an rsync trick.
        scripts.rsync(['%s/' % input], output)

        # `config`, `data`, and `logs` are provided by application pod.
        scripts.mkdir(output / 'config')
        scripts.mkdir(output / 'data')
        scripts.mkdir(output / 'logs')


@rule
@rule.depend('//base:tapeout')
def trim(parameters):
    rootfs = parameters['//base:drydock/rootfs']
    with scripts.using_sudo():
        scripts.rm(rootfs / 'lib', recursive=True)
        scripts.rm(rootfs / 'usr', recursive=True)


@pods.app_specifier
def filebeat_app(parameters):
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
        volumes=[
            pods.Volume(
                name='config-volume',
                path='/opt/filebeat/config',
                data='config-volume/config.tar.gz',
                # Filebeat requires config files owned by the same user
                # running this process.
                user='root', group='root',
            ),
            pods.Volume(
                name='data-volume',
                path='/opt/filebeat/data',
                read_only=False,
            ),
            pods.Volume(
                name='logs-volume',
                path='/opt/filebeat/logs',
                read_only=False,
            ),
            pods.Volume(
                name='host-logs-volume',
                path='/var/log',
                host_path='/var/log',
            ),
        ],
    )


@pods.image_specifier
def filebeat_image(parameters):
    return pods.Image(
        name='filebeat',
        app=parameters['filebeat_app'],
        # Kibana needs to write to `optimize` directory.
        read_only_rootfs=False,
    )


filebeat_image.specify_image.depend('filebeat_app/specify_app')


filebeat_image.write_manifest.depend('//base:tapeout')
filebeat_image.write_manifest.depend('tapeout')
filebeat_image.write_manifest.depend('trim')
