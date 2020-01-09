"""Commands of the build process."""

import logging
from pathlib import Path

import g1.containers.images
from g1.apps import parameters
from g1.bases import argparses
from g1.bases import functionals
from g1.bases.assertions import ASSERT

LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())

PARAMS = parameters.define(
    __name__,
    parameters.Namespace(
        foreman_path=parameters.Parameter(
            '/usr/src/garage/shipyard2/scripts/foreman.sh',
            doc='set foreman path inside builder pod',
            type=str,
        ),
    ),
)

#
# Package-private utilities.
#

base_image_version_arguments = argparses.argument(
    '--base-version',
    type=g1.containers.images.validate_version,
    required=True,
    help='provide base image version',
)

select_image_arguments = functionals.compose(
    argparses.argument(
        '--image-id',
        action=argparses.AppendConstAndValueAction,
        type=g1.containers.images.validate_id,
        dest='image',
        const='id',
        help='add intermediate builder image by id',
    ),
    argparses.argument(
        '--image-nv',
        action=argparses.AppendConstAndValueAction,
        dest='image',
        const='nv',
        metavar=('NAME', 'VERSION'),
        # Sadly it looks like you can't use ``type`` with ``nargs``.
        nargs=2,
        help='add intermediate builder image by name and version',
    ),
    argparses.argument(
        '--image-tag',
        action=argparses.AppendConstAndValueAction,
        type=g1.containers.images.validate_tag,
        dest='image',
        const='tag',
        help='add intermediate builder image by tag',
    ),
)


def import_output_arguments(*, default):
    return argparses.argument(
        '--import-output',
        action=argparses.StoreBoolAction,
        default=default,
        help='also import output image (default: %(default_string)s)',
    )


def get_repo_root_path():
    repo_root_path = Path(__file__).parent.parent.parent.parent
    ASSERT.predicate(repo_root_path / '.git', Path.exists)
    return repo_root_path


def get_ctr_path():
    return ASSERT.predicate(
        Path(__file__).parent.parent.parent / 'scripts' / 'ctr.sh',
        Path.is_file,
    )
