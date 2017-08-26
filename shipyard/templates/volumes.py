"""Build rule helpers for pod data volumes.

Although strictly speaking volumes are a part of pods, their build
process is quite different from pod's; so we put it in this separate
module.
"""

__all__ = [
    'fill_tarball',
]

import grp
import io
import pwd
import tarfile
from pathlib import Path

from garage import asserts
from garage import datetimes


def fill_tarball(parameters, spec, tarball):
    """Fill tarball content from the spec.

    The spec object is usually loaded from a JSON or YAML file.
    """
    for member_spec in spec.get('members', ()):
        _add_member(parameters, member_spec, tarball)


# Only two kinds are supported at the moment.
MEMBER_KINDS = {
    'file': (Path.is_file, tarfile.REGTYPE),
    'dir': (Path.is_dir, tarfile.DIRTYPE),
}


def _add_member(parameters, member_spec, tarball):
    """Add a member to tarball from the spec."""

    # Read member metadata.

    path = member_spec['path']

    asserts.precond(
        not path.startswith('/'),
        'expect relative path: %s', path,
    )

    mode = member_spec.get('mode')  # This is the permission bits.
    mtime = member_spec.get('mtime', int(datetimes.utcnow().timestamp()))
    kind = member_spec.get('kind')

    if kind is not None:
        asserts.in_(kind, MEMBER_KINDS)

    owner = member_spec.get('owner')
    uid = member_spec.get('uid')
    group = member_spec.get('group')
    gid = member_spec.get('gid')

    if owner is None and uid is not None:
        owner = pwd.getpwuid(uid).pw_name

    if uid is None and owner is not None:
        uid = pwd.getpwnam(owner).pw_uid

    asserts.precond(
        (owner is None) == (uid is None),
        'expect both or neither of owner and uid: %s, %s', owner, uid,
    )

    if group is None and gid is not None:
        group = grp.getgrgid(gid).gr_name

    if gid is None and group is not None:
        gid = grp.getgrnam(group).gr_gid

    asserts.precond(
        (group is None) == (gid is None),
        'expect both or neither of group and gid: %s, %s', group, gid,
    )

    #
    # Read member content.
    #
    # We support two ways to specify member content at the moment:
    #   * Define in-place: `content`.
    #   * Read from a path parameter: `content_path_parameter`.
    #

    content = member_spec.get('content')
    content_encoding = member_spec.get('content_encoding', 'utf-8')

    content_path_parameter = member_spec.get('content_path_parameter')

    asserts.precond(
        content is None or content_path_parameter is None,
        'expect at most one of content and content_path_parameter',
    )

    # Create TarInfo object.

    if content is not None:

        asserts.not_none(mode)
        asserts.not_none(kind)
        asserts.not_none(owner)
        asserts.not_none(group)

        content_bytes = content.encode(content_encoding)

        content_path = None
        tarinfo = tarfile.TarInfo(path)
        fileobj = io.BytesIO(content_bytes)

        tarinfo.size = len(content_bytes)

    elif content_path_parameter is not None:
        content_path = parameters[content_path_parameter]
        tarinfo = tarball.gettarinfo(name=content_path, arcname=path)
        fileobj = None

    else:
        content_path = None
        tarinfo = tarfile.TarInfo(path)
        fileobj = None

    if mode is not None:
        tarinfo.mode = mode

    if not tarinfo.mtime:
        tarinfo.mtime = mtime

    if kind is not None:
        predicate, member_type = MEMBER_KINDS[kind]
        asserts.precond(
            content_path is None or predicate(content_path),
            'expect %s-kind: %s', kind, content_path,
        )
        tarinfo.type = member_type

    if owner is not None:
        asserts.not_none(uid)
        tarinfo.uname = owner
        tarinfo.uid = uid

    if group is not None:
        asserts.not_none(gid)
        tarinfo.gname = group
        tarinfo.gid = gid

    # Finally, add TarInfo object to the tarball.

    # Skip adding '.', which seems to be a nice thing to do.
    if path != '.':
        _add_tarinfo(tarinfo, content_path, fileobj, tarball)

    if content_path and content_path.is_dir():
        for child_path in content_path.rglob('*'):

            child_tarinfo = tarball.gettarinfo(
                name=child_path,
                arcname=str(path / child_path.relative_to(content_path)),
            )

            if owner is not None:
                asserts.not_none(uid)
                child_tarinfo.uname = owner
                child_tarinfo.uid = uid

            if group is not None:
                asserts.not_none(gid)
                child_tarinfo.gname = group
                child_tarinfo.gid = gid

            _add_tarinfo(child_tarinfo, child_path, None, tarball)


def _add_tarinfo(tarinfo, path, fileobj, tarball):
    asserts.precond(
        path is None or fileobj is None,
        'expect at most one of path and fileobj',
    )
    if path is not None and path.is_file():
        with path.open('rb') as fileobj:
            tarball.addfile(tarinfo, fileobj=fileobj)
    else:
        tarball.addfile(tarinfo, fileobj=fileobj)
