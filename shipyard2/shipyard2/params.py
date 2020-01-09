# NOTE: Do NOT put these into shipyard2/__init__.py since we don't want
# shipyard2.rules to have access to these parameters.

from pathlib import Path

from g1.apps import parameters
from g1.bases.assertions import ASSERT

import shipyard2

PARAMS = parameters.define(
    'shipyard2',
    parameters.Namespace(
        sources=parameters.Parameter(
            [str(shipyard2.REPO_ROOT_PATH)],
            doc='host paths to source repositories',
            type=list,
        ),
        release=parameters.Parameter(
            '',
            doc='host path to release repository',
            type=str,
        ),
        base_version=parameters.Parameter(
            '',
            doc='base image version',
            type=str,
        ),
    ),
)


def get_source_host_paths():
    return ASSERT.not_empty(
        ASSERT.all(
            list(map(Path, PARAMS.sources.get())), shipyard2.is_source_repo
        )
    )


def get_source_paths():
    return list(map(get_source_path, get_source_host_paths()))


def get_source_path(host_source_path):
    return Path('/usr/src') / host_source_path.name


def get_release_host_path():
    return ASSERT.predicate(
        Path(ASSERT.true(PARAMS.release.get())),
        Path.is_dir,
    )
