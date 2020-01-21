__all__ = [
    'dump',
    'generate_release_metadata',
]

import dataclasses
import json
import typing

from g1 import scripts
from g1.bases.assertions import ASSERT


@dataclasses.dataclass(frozen=True)
class ReleaseMetadata:

    @dataclasses.dataclass(frozen=True)
    class Source:
        url: str
        revision: str
        dirty: bool

    sources: typing.List[Source]


def generate_release_metadata(parameters, metadata_path):
    dump(
        ReleaseMetadata(
            sources=[
                _git_get_source(repo_path)
                for repo_path in parameters['//bases:roots']
            ],
        ),
        metadata_path,
    )


def _git_get_source(source):
    with scripts.using_cwd(source), scripts.doing_capture_output():
        return ReleaseMetadata.Source(
            url=_git_get_url(source),
            revision=_git_get_revision(),
            dirty=_git_get_dirty(),
        )


def _git_get_url(source):
    proc = scripts.run(['git', 'remote', '--verbose'])
    for remote in proc.stdout.decode('utf8').split('\n'):
        remote = remote.split()
        if remote[0] == 'origin':
            return remote[1]
    return ASSERT.unreachable('expect remote origin: {}', source)


def _git_get_revision():
    proc = scripts.run(['git', 'log', '-1', '--format=format:%H'])
    return proc.stdout.decode('ascii').strip()


def _git_get_dirty():
    proc = scripts.run(['git', 'status', '--porcelain'])
    for status in proc.stdout.decode('utf8').split('\n'):
        # Be careful of empty line!
        if status and not status.startswith('  '):
            return True
    return False


def dump(obj, path):
    scripts.write_bytes(
        json.dumps(dataclasses.asdict(obj), indent=4).encode('ascii'),
        path,
    )
