"""File spec for generating tarball content, etc."""

__all__ = [
    'make_filespec',
]

import grp
import pwd
from collections import namedtuple

from garage import datetimes
from garage import scripts
from garage.assertions import ASSERT


FileSpec = namedtuple('FileSpec', [
    'path',

    'mode',  # Optional.

    'mtime',

    'kind',  # Either 'file' or 'dir'.

    'owner', 'uid',
    'group', 'gid',

    'content', 'content_path',  # Use either one of them.
    'content_encoding',
])


def make_filespec(**data):
    """Make FileSpec object from input data."""
    spec = {}

    path = scripts.ensure_path(data['path'])
    ASSERT(not path.is_absolute(), 'expect relative path: %s', path)
    spec['path'] = path

    spec['mode'] = data.get('mode')

    mtime = data.get('mtime')
    if mtime is None:
        mtime = int(datetimes.utcnow().timestamp())
    spec['mtime'] = mtime

    spec['kind'] = ASSERT.in_(data.get('kind'), (None, 'dir', 'file'))

    # XXX Calling getpwuid or getpwnam here might not be a great idea
    # since the user name might not exist on this system; what should I
    # do here instead?
    owner = data.get('owner')
    uid = data.get('uid')
    if owner is None and uid is not None:
        owner = pwd.getpwuid(uid).pw_name
    elif uid is None and owner is not None:
        uid = pwd.getpwnam(owner).pw_uid
    ASSERT(
        (owner is None) == (uid is None),
        'expect both or neither of owner and uid: %s, %s', owner, uid,
    )
    spec['owner'] = owner
    spec['uid'] = uid

    # XXX Ditto.
    group = data.get('group')
    gid = data.get('gid')
    if group is None and gid is not None:
        group = grp.getgrgid(gid).gr_name
    elif gid is None and group is not None:
        gid = grp.getgrnam(group).gr_gid
    ASSERT(
        (group is None) == (gid is None),
        'expect both or neither of group and gid: %s, %s', group, gid,
    )
    spec['group'] = group
    spec['gid'] = gid

    content = data.get('content')
    content_path = data.get('content_path')
    ASSERT(
        content is None or content_path is None,
        'expect at most one of content and content_path',
    )
    if content is not None:
        ASSERT.not_none(spec['mode'])
        ASSERT.not_none(spec['kind'])
        ASSERT.not_none(spec['owner'])
        ASSERT.not_none(spec['group'])
    spec['content'] = content
    spec['content_path'] = scripts.ensure_path(content_path)

    spec['content_encoding'] = data.get('content_encoding', 'utf-8')

    return FileSpec(**spec)
