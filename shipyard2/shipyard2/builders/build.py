__all__ = [
    'cmd_build',
]

import contextlib
import json
import logging
import tempfile
from pathlib import Path

import foreman

import g1.containers.bases
import g1.containers.images
import g1.containers.pods
from g1.bases import argparses
from g1.bases.assertions import ASSERT

from shipyard2 import builders

LOG = logging.getLogger(__name__)


@argparses.begin_parser(
    'build',
    **builders.make_help_kwargs('build intermediate builder image'),
)
@argparses.argument(
    '--builder-id',
    type=g1.containers.pods.validate_id,
    help='set builder pod id (default to a random one)',
)
@builders.base_image_version_arguments
@builders.select_image_arguments
@argparses.argument(
    '--volume',
    action='append',
    help='add volume of the form "source:target[:ro]"',
)
@argparses.argument(
    '--rule',
    action='append',
    type=foreman.Label.parse,
    help='add build rule',
)
@builders.import_output_arguments(default=True)
@g1.containers.images.image_output_arguments
@argparses.end
def cmd_build(args):
    g1.containers.bases.assert_root_privilege()
    ASSERT.not_predicate(args.output, g1.containers.bases.lexists)
    builder_id = _get_builder_id(args)
    builder_config = _generate_builder_config(
        apps=_get_apps(args),
        images=_get_images(args),
        volumes=_get_volumes(args),
    )
    ctr_exec = builders.PARAMS.ctr_exec.get()
    with contextlib.ExitStack() as stack:
        tempdir_path = Path(
            stack.enter_context(
                tempfile.TemporaryDirectory(dir=args.output.parent)
            )
        )
        builder_config_path = tempdir_path / 'builder.json'
        builder_config_path.write_text(json.dumps(builder_config))
        if builders.is_debug():
            LOG.debug('builder config: %s', builder_config_path.read_text())
        # The builder pod might not be cleaned up when `ctr pods run`
        # fails; so let's always do `ctr pods remove` on our way out.
        stack.callback(builders.run, [ctr_exec, 'pods', 'remove', builder_id])
        LOG.info('start builder pod')
        builders.run([
            ctr_exec,
            'pods',
            'run',
            *('--id', builder_id),
            builder_config_path,
        ])
        LOG.info('export intermediate builder image to: %s', args.output)
        rootfs_path = tempdir_path / 'rootfs'
        builders.run([
            ctr_exec,
            'pods',
            'export-overlay',
            builder_id,
            rootfs_path,
        ])
        builders.run([
            ctr_exec,
            'images',
            'build',
            *('--rootfs', rootfs_path),
            args.name,
            args.version,
            args.output,
        ])
        if args.import_output:
            builders.run([ctr_exec, 'images', 'import', args.output])
    return 0


def _get_builder_id(args):
    if args.builder_id is None:
        builder_id = g1.containers.pods.generate_id()
        LOG.info('use builder pod id: %s', builder_id)
    else:
        builder_id = g1.containers.pods.validate_id(args.builder_id)
    return builder_id


def _generate_builder_config(apps, images, volumes):
    return {
        'name': 'builder',
        'version': '0.0.1',
        'apps': apps,
        'images': images,
        'volumes': volumes,
    }


_INIT_BASE_DATA = (
    'adduser --disabled-password --gecos "" plumber',
    'echo "plumber ALL=(ALL:ALL) NOPASSWD: ALL" > /etc/sudoers.d/99-plumber',
    'chmod 440 /etc/sudoers.d/99-plumber',
    # foreman needs at least python3; let's use 3.8 to be safe.
    # TODO: Get distro (bionic) from `ctr images build-base`.
    # pylint: disable=line-too-long
    'apt-get install --yes software-properties-common',
    'add-apt-repository --yes "deb http://us.archive.ubuntu.com/ubuntu/ bionic main restricted universe"',
    'add-apt-repository --yes "deb http://us.archive.ubuntu.com/ubuntu/ bionic-updates main restricted universe"',
    'add-apt-repository --yes "deb http://security.ubuntu.com/ubuntu/ bionic-security main restricted universe"',
    'apt-get update',
    'apt-get install --yes python3.8',
    'update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.8 1',
    'update-alternatives --set python3 /usr/bin/python3.8',
    # pylint: enable=line-too-long
)


def _get_apps(args):
    builder_script = []
    if not args.image:
        LOG.info('no intermediate builder images; init base data')
        builder_script.extend(_INIT_BASE_DATA)
    if args.rule:
        builder_script.append(
            'sudo -u plumber -g plumber "%s" build %s %s' % (
                builders.PARAMS.foreman_path.get(),
                '--debug' if builders.is_debug() else '',
                ' '.join('"%s"' % rule for rule in args.rule),
            )
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


def _get_images(args):
    images = [
        {
            'name': builders.BASE,
            'version': args.base_version,
        },
        {
            'name': builders.BUILDER_BASE,
            'version': args.base_version,
        },
    ]
    for image in args.image or ():
        if image[0] == 'id':
            images.append({'id': image[1]})
        elif image[0] == 'nv':
            images.append({
                'name':
                g1.containers.images.validate_name(image[1][0]),
                'version':
                g1.containers.images.validate_version(image[1][1]),
            })
        elif image[0] == 'tag':
            images.append({'tag': image[1]})
        else:
            ASSERT.unreachable('unknown image arg: {}', image)
    return images


def _get_volumes(args):
    volumes = [
        {
            'source': str(builders.get_repo_root_path()),
            'target': '/usr/src/garage',
            'read_only': True
        },
    ]
    for volume in args.volume or ():
        parts = volume.split(':')
        if ASSERT.in_(len(parts), (2, 3)) == 3:
            source, target, read_only = parts
            read_only = read_only == 'ro'
        else:
            source, target = parts
            read_only = False
        volumes.append({
            'source': source,
            'target': target,
            'read_only': read_only,
        })
    return volumes
