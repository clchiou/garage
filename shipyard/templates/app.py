"""Application images and pods build rule templates."""

__all__ = [
    'define_image',
]

import hashlib
import logging
import os

from garage import scripts

from foreman import rule

from . import utils


LOG = logging.getLogger(__name__)


def define_image(image_name, make_image_manifest=None):
    """Define IMAGE_NAME/write_manifest and IMAGE_NAME/build_image rule."""

    # TODO: Encrypt and/or sign the image

    @rule(image_name + '/write_manifest')
    @rule.depend('//base:tapeout')
    def write_manifest(parameters):
        """Create Appc image manifest file."""
        LOG.info('write appc image manifest: %s', image_name)
        manifest = {
            'acKind': 'ImageManifest',
            'acVersion': '0.8.10',
            'name': image_name,
            'labels': [
                {
                    'name': 'arch',
                    'value': 'amd64',
                },
                {
                    'name': 'os',
                    'value': 'linux',
                },
            ],
        }
        if make_image_manifest:
            manifest = make_image_manifest(parameters, manifest)
        utils.write_json_to(manifest, parameters['//base:drydock/manifest'])

    @rule(image_name + '/build_image')
    @rule.depend('//base:tapeout')
    @rule.depend(image_name + '/write_manifest')
    def build_image(parameters):
        """Build Appc container image."""
        output_dir = parameters['//base:output'] / image_name
        LOG.info('build appc image: %s', output_dir)

        image_data_dir = parameters['//base:drydock/build']
        scripts.ensure_file(image_data_dir / 'manifest')
        scripts.ensure_directory(image_data_dir / 'rootfs')

        scripts.mkdir(output_dir)
        image_path = output_dir / 'image.aci'
        if image_path.exists():
            LOG.warning('overwrite: %s', image_path)
        image_checksum_path = output_dir / 'sha512'

        scripts.pipeline(
            [
                lambda: scripts.tar_create(
                    image_data_dir, ['manifest', 'rootfs'],
                    tarball_path=None,
                    tar_extra_flags=['--numeric-owner'],
                ),
                lambda: _compute_sha512(image_checksum_path),
                lambda: scripts.gzip(speed=9),
            ],
            # Don't close file opened from image_path here because
            # pipeline() will close it
            pipe_output=image_path.open('wb'),
        )
        scripts.ensure_file(image_path)
        scripts.ensure_file(image_checksum_path)

    return write_manifest, build_image


def _compute_sha512(sha512_file_path):
    hasher = hashlib.sha512()
    input_fd = scripts.get_stdin()
    output_fd = scripts.get_stdout()
    while True:
        data = os.read(input_fd, 4096)
        if not data:
            break
        hasher.update(data)
        os.write(output_fd, data)
    sha512_file_path.write_text('%s\n' % hasher.hexdigest())
