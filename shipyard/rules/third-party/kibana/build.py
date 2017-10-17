"""Build (standard) Kibana image."""

from foreman import get_relpath, rule

from garage import scripts

from templates import common, pods


common.define_archive(
    uri='https://artifacts.elastic.co/downloads/kibana/kibana-5.6.3-linux-x86_64.tar.gz',
    filename='kibana-5.6.3-linux-x86_64.tar.gz',
    output='kibana-5.6.3-linux-x86_64',
    checksum='md5-94e5dde112d943fa06072e9da8ba4f6f',
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

        output = parameters['//base:drydock/rootfs'] / 'opt/kibana'
        scripts.mkdir(output)

        # `config`, `data`, and `logs` are provided by application pod.
        scripts.mkdir(output / 'config')
        scripts.mkdir(output / 'data')
        scripts.mkdir(output / 'logs')

        scripts.rsync(
            [input / fn for fn in (
                'node',
                'node_modules',
                'optimize',
                'package.json',
                'plugins',
                'src',
            )],
            output,
        )

        # Kibana needs to write to `optimize` directory.
        scripts.execute([
            'chown', '--recursive', 'nobody:nogroup', output / 'optimize',
        ])


@pods.app_specifier
def kibana_app(parameters):
    return pods.App(
        name='kibana',
        exec=[
            'node/bin/node',
            'src/cli',
        ],
        working_directory='/opt/kibana',
        volumes=[
            pods.Volume(
                name='config-volume',
                path='/opt/kibana/config',
                data='config-volume/config.tar.gz',
            ),
            pods.Volume(
                name='data-volume',
                path='/opt/kibana/data',
                read_only=False,
            ),
            pods.Volume(
                name='logs-volume',
                path='/opt/kibana/logs',
                read_only=False,
            ),
        ],
        ports=[
            pods.Port(
                name='web',
                protocol='tcp',
                port=5601,
                host_port=5601,
            ),
        ],
    )


@pods.image_specifier
def kibana_image(parameters):
    return pods.Image(
        name='kibana',
        app=parameters['kibana_app'],
        # Kibana needs to write to `optimize` directory.
        read_only_rootfs=False,
    )


kibana_image.specify_image.depend('kibana_app/specify_app')


kibana_image.write_manifest.depend('//base:tapeout')
kibana_image.write_manifest.depend('tapeout')
