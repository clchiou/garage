__all__ = [
    'build_image',
]

import contextlib
import dataclasses
import json
import logging
import tempfile
from pathlib import Path

import foreman

from g1.bases.assertions import ASSERT
from g1.containers import scripts as ctr_scripts

import shipyard2

from . import utils

LOG = logging.getLogger(__name__)


def build_image(
    *,
    parameters,
    builder_id,
    builder_images,
    name,
    version,
    rules,
    output,
):
    root_host_paths = parameters['//bases:roots']
    builder_config = _generate_builder_config(
        name=name,
        version=version,
        apps=_get_apps(
            builder_images,
            root_host_paths,
            rules,
        ),
        images=_get_images(
            builder_images,
            ASSERT.not_none(parameters['//images/bases:base/version']),
        ),
        mounts=_get_mounts(
            root_host_paths,
            parameters['//releases:shipyard-data'],
            name,
            rules,
        ),
    )
    with contextlib.ExitStack() as stack:
        tempdir_path = Path(
            stack.enter_context(
                tempfile.TemporaryDirectory(dir=output.parent)
            )
        )
        builder_config_path = tempdir_path / 'builder.json'
        builder_config_path.write_text(json.dumps(builder_config))
        if shipyard2.is_debug():
            LOG.debug('builder config: %s', builder_config_path.read_text())
        # The builder pod might not be cleaned up when `ctr pods run`
        # fails; so let's always do `ctr pods remove` on our way out.
        stack.callback(ctr_scripts.ctr_remove_pod, builder_id)
        LOG.info('start builder pod')
        ctr_scripts.ctr_run_pod(builder_id, builder_config_path)
        LOG.info('export intermediate builder image to: %s', output)
        rootfs_path = tempdir_path / 'rootfs'
        stack.callback(utils.sudo_rm, rootfs_path)
        ctr_scripts.ctr([
            'pods',
            'export-overlay',
            builder_id,
            rootfs_path,
        ])
        ctr_scripts.ctr_build_image(
            utils.get_builder_name(name), version, rootfs_path, output
        )
        ctr_scripts.ctr_import_image(output)


def _generate_builder_config(name, version, apps, images, mounts):
    return {
        'name': utils.get_builder_name(name),
        'version': version,
        'apps': apps,
        'images': images,
        'mounts': mounts,
    }


_INITIALIZE_BUILDER = (
    # pylint: disable=line-too-long
    'adduser --disabled-password --gecos "" plumber',
    'echo "plumber ALL=(ALL:ALL) NOPASSWD: ALL" > /etc/sudoers.d/99-plumber',
    'chmod 440 /etc/sudoers.d/99-plumber',
    # TODO: Get distro (bionic) from `ctr images build-base`.
    'apt-get --yes install software-properties-common',
    # Clear the default repositories from `ctr images build-base` as
    # they conflict with mime.
    'echo -n > /etc/apt/sources.list',
    'add-apt-repository --yes "deb http://us.archive.ubuntu.com/ubuntu/ bionic main restricted universe"',
    'add-apt-repository --yes "deb http://us.archive.ubuntu.com/ubuntu/ bionic-updates main restricted universe"',
    'add-apt-repository --yes "deb http://security.ubuntu.com/ubuntu/ bionic-security main restricted universe"',
    'apt-get --yes update',
    'apt-get --yes full-upgrade',
    # foreman needs at least python3; let's use 3.8 to be safe.
    'apt-get --yes install python3.8',
    'update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.8 1',
    'update-alternatives --set python3 /usr/bin/python3.8',
    # pylint: enable=line-too-long
)


def _get_apps(builder_images, root_host_paths, rules):
    builder_script = []
    if not builder_images:
        LOG.info('no intermediate builder images; initialize builder')
        builder_script.extend(_INITIALIZE_BUILDER)
    if rules:
        builder_script.append(
            ' '.join([
                'sudo',
                *('-u', 'plumber'),
                *('-g', 'plumber'),
                '/usr/src/garage/shipyard2/scripts/foreman.sh',
                'build',
                *(('--debug', ) if shipyard2.is_debug() else ()),
                *_foreman_make_path_args(root_host_paths),
                *('--parameter', '//bases:inside-builder-pod=true'),
                *map(str, rules),
            ])
        )
    ASSERT.not_empty(builder_script)
    return [
        {
            'name': 'builder',
            'type': 'oneshot',
            'exec': ['/bin/bash', '-c', '; '.join(builder_script)],
            'user': 'root',
            'group': 'root',
        },
    ]


def _foreman_make_path_args(root_host_paths):
    root_paths = list(map(_root_host_to_target, root_host_paths))
    for root_path in root_paths:
        yield '--path'
        yield str(root_path / 'shipyard2' / 'rules')
    yield '--parameter'
    yield '//bases:roots=%s' % ','.join(map(str, root_paths))


def _get_images(builder_images, base_version):
    return [
        {
            'name': shipyard2.BASE,
            'version': base_version,
        },
        {
            'name': utils.get_builder_name(shipyard2.BASE),
            'version': base_version,
        },
        *map(dataclasses.asdict, builder_images),
    ]


def _get_mounts(root_host_paths, shipyard_data_path, name, rules):
    mounts = [{
        'source': str(root_host_path),
        'target': str(_root_host_to_target(root_host_path)),
        'read_only': True,
    } for root_host_path in root_host_paths]
    if shipyard_data_path is not None:
        image_data_path = shipyard_data_path / 'image-data'
        if _should_mount_image_data(image_data_path, name, rules):
            mounts.append({
                'source': str(image_data_path),
                'target': '/usr/src/image-data',
                'read_only': True,
            })
    return mounts


def _should_mount_image_data(image_data_path, name, rules):
    """True if we should mount image-data directory.

    Check presence of the following directories:
    * <image-data>/images/<image-path>/<image-name>.
    * <image-data>/<rule-path>.
    """
    if (image_data_path / foreman.get_relpath() / name).is_dir():
        return True
    for rule in rules:
        if (image_data_path / rule.path).is_dir():
            return True
    return False


def _root_host_to_target(root_host_path):
    return Path('/usr/src') / root_host_path.name
