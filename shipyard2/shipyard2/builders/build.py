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
from g1 import scripts
from g1.bases import argparses
from g1.bases.assertions import ASSERT

import shipyard2
from shipyard2 import builders
from shipyard2 import params

LOG = logging.getLogger(__name__)


@argparses.begin_parser(
    'build',
    **shipyard2.make_help_kwargs('build intermediate builder image'),
)
@argparses.argument(
    '--builder-id',
    type=g1.containers.pods.validate_id,
    help='set builder pod id (default to a random one)',
)
@builders.base_image_version_arguments
@builders.select_image_arguments
@argparses.argument(
    '--mount',
    action='append',
    help='add mount of the form "source:target[:ro]"',
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
        mounts=_get_mounts(args),
    )
    ctr_path = shipyard2.get_ctr_path()
    with contextlib.ExitStack() as stack:
        tempdir_path = Path(
            stack.enter_context(
                tempfile.TemporaryDirectory(dir=args.output.parent)
            )
        )
        builder_config_path = tempdir_path / 'builder.json'
        builder_config_path.write_text(json.dumps(builder_config))
        if shipyard2.is_debug():
            LOG.debug('builder config: %s', builder_config_path.read_text())
        # The builder pod might not be cleaned up when `ctr pods run`
        # fails; so let's always do `ctr pods remove` on our way out.
        stack.callback(scripts.run, [ctr_path, 'pods', 'remove', builder_id])
        LOG.info('start builder pod')
        scripts.run([
            ctr_path,
            'pods',
            'run',
            *('--id', builder_id),
            builder_config_path,
        ])
        LOG.info('export intermediate builder image to: %s', args.output)
        rootfs_path = tempdir_path / 'rootfs'
        scripts.run([
            ctr_path,
            'pods',
            'export-overlay',
            builder_id,
            rootfs_path,
        ])
        scripts.run([
            ctr_path,
            'images',
            'build',
            *('--rootfs', rootfs_path),
            args.name,
            args.version,
            args.output,
        ])
        if args.import_output:
            scripts.run([ctr_path, 'images', 'import', args.output])
    return 0


def _get_builder_id(args):
    if args.builder_id is None:
        builder_id = g1.containers.pods.generate_id()
        LOG.info('use builder pod id: %s', builder_id)
    else:
        builder_id = g1.containers.pods.validate_id(args.builder_id)
    return builder_id


def _generate_builder_config(apps, images, mounts):
    return {
        'name': 'builder',
        'version': '0.0.1',
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


def _get_apps(args):
    builder_script = []
    if not args.image:
        LOG.info('no intermediate builder images; initialize builder')
        builder_script.extend(_INITIALIZE_BUILDER)
    if args.rule:
        builder_script.append(
            ' '.join([
                'sudo',
                *('-u', 'plumber'),
                *('-g', 'plumber'),
                str(shipyard2.get_foreman_path()),
                'build',
                *(('--debug', ) if shipyard2.is_debug() else ()),
                *_foreman_make_path_args(),
                *(
                    '--parameter',
                    '//bases:roots=%s' %
                    ','.join(map(str, params.get_source_paths())),
                ),
                *map(str, args.rule),
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


def _foreman_make_path_args():
    for path in params.get_source_paths():
        yield '--path'
        yield str(path / 'shipyard2' / 'rules')


def _get_images(args):
    images = [
        {
            'name': shipyard2.BASE,
            'version': args.base_version,
        },
        {
            'name': shipyard2.get_builder_name(shipyard2.BASE),
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


def _get_mounts(args):
    mounts = [{
        'source': str(host_path),
        'target': str(params.get_source_path(host_path)),
        'read_only': True,
    } for host_path in params.get_source_host_paths()]
    for mount in args.mount or ():
        parts = mount.split(':')
        if ASSERT.in_(len(parts), (2, 3)) == 3:
            source, target, read_only = parts
            read_only = read_only == 'ro'
        else:
            source, target = parts
            read_only = False
        mounts.append({
            'source': source,
            'target': target,
            'read_only': read_only,
        })
    return mounts
