import logging
import subprocess
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
        ctr_exec=parameters.Parameter(
            'ctr',
            doc='set ctr executable (default to look up from PATH)',
            type=str,
        ),
        foreman_path=parameters.Parameter(
            '/usr/src/garage/shipyard2/scripts/foreman.sh',
            doc='set foreman path inside builder pod',
            type=str,
        ),
        dry_run=parameters.Parameter(
            False,
            doc='whether to dry-run the build process',
            type=bool,
        ),
    ),
)

BASE = 'base'
BUILDER_BASE = 'builder-base'

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


def is_debug():
    return logging.getLogger().isEnabledFor(logging.DEBUG)


def get_repo_root_path():
    repo_root_path = Path(__file__).parent.parent.parent.parent
    ASSERT.predicate(repo_root_path / '.git', Path.exists)
    return repo_root_path


def make_help_kwargs(help_text):
    return {
        'help': help_text,
        'description': '%s%s.' % (help_text[0].upper(), help_text[1:]),
    }


def run(args):
    args = list(map(str, args))
    LOG.debug('run: %s', args)
    if not PARAMS.dry_run.get():
        subprocess.run(args, check=True)
