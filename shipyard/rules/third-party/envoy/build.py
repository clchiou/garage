"""Build (standard) envoy image."""

from foreman import define_parameter, rule

from garage import asserts
from garage import scripts

from templates import pods


(define_parameter('version')
 .with_doc('Envoy version.')
 .with_default('f8dbb065177e61d3b6fc74eda59c59732b07dfbd'))


@rule
@rule.reverse_depend('//base:tapeout')
def tapeout(parameters):
    """Copy envoy to the tapeout location.

    There is no build rule because we do not build envoy from source;
    instead, we directly use binaries from CI.
    """

    envoy_path = parameters['//base:input'] / 'envoy'
    scripts.ensure_file(envoy_path)

    # Just a sanity check.
    asserts.in_(
        'envoy version: %s/Clean/RELEASE' % parameters['version'],
        (scripts.execute([envoy_path, '--version'], capture_stdout=True)
         .stdout.decode('ascii')),
    )

    rootfs = parameters['//base:drydock/rootfs']
    bin_dir_path = rootfs / 'usr/local/bin'

    with scripts.using_sudo():
        scripts.mkdir(bin_dir_path)
        scripts.cp(envoy_path, bin_dir_path)
        scripts.execute(['chown', '--recursive', 'root:root', bin_dir_path])


@rule
@rule.depend('//base:tapeout')
def trim_usr(parameters):
    """Trim /usr/lib and /usr/local/lib.

    This is a hackish optimization: since envoy does not need libraries
    under /usr, we may remove them and reduce the image size.

    Unfortunately ld.so.cache will still contain libraries under /usr.
    """
    rootfs = parameters['//base:drydock/rootfs']
    with scripts.using_sudo():
        scripts.rm(rootfs / 'usr/lib', recursive=True)
        scripts.rm(rootfs / 'usr/local/lib', recursive=True)


@pods.app_specifier
def envoy_app(parameters):
    return pods.App(
        name='envoy',
        exec=[
            '/usr/local/bin/envoy',
            '--config-path', '/srv/envoy/config.yaml',
        ],
        # XXX: /dev/console is only writable by root unfortunately.
        user='root', group='root',
        volumes=[
            pods.Volume(
                name='envoy-volume',
                path='/srv/envoy',
                data='envoy-volume/envoy-config.tar.gz',
            ),
        ],
        ports=[
            # Serve HTTPS on host port 443.
            pods.Port(
                name='web',
                protocol='tcp',
                port=8443,
                host_port=443,
            ),
            # Serve admin interface on an deploy-time allocated port.
            pods.Port(
                name='admin',
                protocol='tcp',
                port=9000,
            ),
        ],
    )


@pods.image_specifier
def envoy_image(parameters):
    return pods.Image(
        name='envoy',
        app=parameters['envoy_app'],
        # XXX: envoy needs writable access to /dev/shm for the hot
        # restart shared memory region (although I am not using that
        # feature, it seems not possible to disable that).
        read_only_rootfs=False,
    )


envoy_image.specify_image.depend('envoy_app/specify_app')


envoy_image.write_manifest.depend('trim_usr')
envoy_image.write_manifest.depend('tapeout')
