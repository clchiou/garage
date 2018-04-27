"""Build rule helpers for pod data volumes.

Although strictly speaking volumes are a part of pods, their build
process is quite different from pod's; so we put it in this separate
module.
"""

__all__ = [
    'fill_tarball',
    'apply_filespec_to_tarball',
]

import io
import tarfile
from pathlib import Path

from garage.assertions import ASSERT

from templates import filespecs


def fill_tarball(spec, tarball):
    """Fill tarball content from the spec.

    The spec object is usually loaded from a JSON or YAML file.
    """
    for member_spec in spec.get('members', ()):
        spec = filespecs.make_filespec(member_spec)
        apply_filespec_to_tarball(spec, tarball)


def apply_filespec_to_tarball(spec, tarball):
    tarinfo, input_path, fileobj = _make_tarinfo(tarball, spec)

    # Skip adding '.', which seems to be a nice thing to do.
    if spec.path != Path('.'):
        _add_file(tarinfo, input_path, fileobj, tarball)

    if input_path and input_path.is_dir():
        for child_path in input_path.rglob('*'):

            relpath = child_path.relative_to(input_path)

            # XXX `gettarinfo` of Python 3.5 doesn't accept path-like.
            child_tarinfo = tarball.gettarinfo(
                name=str(child_path),
                arcname=str(spec.path / relpath),
            )

            if spec.owner is not None:
                child_tarinfo.uname = spec.owner
                child_tarinfo.uid = spec.uid

            if spec.group is not None:
                child_tarinfo.gname = spec.group
                child_tarinfo.gid = spec.gid

            _add_file(child_tarinfo, child_path, None, tarball)


# Only two kinds are supported at the moment.
MEMBER_KINDS = {
    'file': (Path.is_file, tarfile.REGTYPE),
    'dir': (Path.is_dir, tarfile.DIRTYPE),
}


def _make_tarinfo(tarball, spec):
    """Make TarInfo object from spec."""

    if spec.content is not None:
        content_bytes = spec.content.encode(spec.content_encoding)
        # XXX Python 3.5 probably doesn't accept path-like.
        tarinfo = tarfile.TarInfo(str(spec.path))
        tarinfo.size = len(content_bytes)
        input_path = None
        fileobj = io.BytesIO(content_bytes)
    elif spec.content_path is not None:
        # XXX `gettarinfo` of Python 3.5 doesn't accept path-like.
        tarinfo = tarball.gettarinfo(
            name=str(spec.content_path), arcname=spec.path)
        input_path = spec.content_path
        fileobj = None
    else:
        # XXX Python 3.5 probably doesn't accept path-like.
        tarinfo = tarfile.TarInfo(str(spec.path))
        input_path = None
        fileobj = None

    if spec.mode is not None:
        tarinfo.mode = spec.mode

    if not tarinfo.mtime:
        tarinfo.mtime = spec.mtime

    if spec.kind is not None:
        predicate, member_type = MEMBER_KINDS[spec.kind]
        ASSERT(
            input_path is None or predicate(input_path),
            'expect %s-kind: %s', spec.kind, input_path,
        )
        tarinfo.type = member_type

    if spec.owner is not None:
        tarinfo.uname = spec.owner
        tarinfo.uid = spec.uid

    if spec.group is not None:
        tarinfo.gname = spec.group
        tarinfo.gid = spec.gid

    return tarinfo, input_path, fileobj


def _add_file(tarinfo, path, fileobj, tarball):
    """Add file to tarball, either from path or fileobj."""
    ASSERT(
        path is None or fileobj is None,
        'expect at most one of path and fileobj',
    )
    if path is not None and path.is_file():
        with path.open('rb') as input_file:
            tarball.addfile(tarinfo, fileobj=input_file)
    else:
        tarball.addfile(tarinfo, fileobj=fileobj)
