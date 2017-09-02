"""Build envoy image and pod."""

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
        'envoy  version: %s/Clean/RELEASE' % parameters['version'],
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
    """Default App object for envoy container image."""
    return pods.App(
        name='envoy',
        exec=['/usr/local/bin/envoy'],
    )


@pods.image_specifier
def envoy_image(parameters):
    """Default envoy container image."""
    return pods.Image(
        name='envoy',
        app=parameters['envoy_app'],
    )


# TODO: Build pod (where should I pull configuration file from?).


envoy_image.specify_image.depend('envoy_app/specify_app')


envoy_image.write_manifest.depend('trim_usr')
envoy_image.write_manifest.depend('tapeout')
