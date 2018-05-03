"""Helpers for writing templates (not for build rules directly)."""

__all__ = [
    'parse_common_args',

    'tapeout_filespecs',
    'tapeout_files',

    'write_json_to',
]

import functools
import json

from garage import scripts
from garage.assertions import ASSERT

from templates import filespecs


def parse_common_args(template):
    """Parse template arguments by the convention."""

    # Don't use setdefault() in parsers since arguments may be
    # None-valued.

    def parse_root(kwargs, arg):
        root = kwargs.get(arg)
        kwargs[arg] = root or '//base:root'

    def parse_name(kwargs, arg):
        name = kwargs.get(arg)
        if not name:
            name = ''
        elif not name.endswith('/'):
            name += '/'
        kwargs[arg] = name

    parsers = []
    for arg, anno in template.__annotations__.items():
        if anno == 'root':
            parsers.append(functools.partial(parse_root, arg=arg))
        elif anno == 'name':
            parsers.append(functools.partial(parse_name, arg=arg))
        else:
            raise AssertionError('cannot parse: %s' % anno)

    @functools.wraps(template)
    def wrapper(*args, **kwargs):
        for parser in parsers:
            parser(kwargs)
        return template(*args, **kwargs)

    return wrapper


def tapeout_filespecs(parameters, top_path, spec_dicts):
    """Generate and tapeout files from file spec."""
    rootfs = parameters['//base:drydock/rootfs']
    top_path = scripts.ensure_path(top_path)
    ASSERT.false(top_path.is_absolute())
    top_path = rootfs / top_path
    with scripts.using_sudo():
        scripts.mkdir(top_path)
        for spec_dict in spec_dicts:
            spec = filespecs.make_filespec(spec_dict)
            path = top_path / spec.path
            if spec.kind == 'file':
                if spec.content is not None:
                    scripts.tee(
                        spec.content.encode(spec.content_encoding), path)
                else:
                    ASSERT.not_none(spec.content_path)
                    scripts.cp(spec.content_path, path)
                recursive = []
            else:
                scripts.mkdir(path)
                if spec.content_path:
                    ASSERT.true(spec.content_path.is_dir())
                    # Appending '/' to src is an rsync trick.
                    scripts.rsync(['%s/' % spec.content_path], path)
                recursive = ['--recursive']
            # Ignore spec.mtime...
            if spec.mode is not None:
                scripts.execute(['chmod', '0%o' % spec.mode, path])
            if spec.owner:
                scripts.execute(['chown'] + recursive + [spec.owner, path])
            if spec.group:
                scripts.execute(['chgrp'] + recursive + [spec.group, path])


def tapeout_files(parameters, paths, excludes=()):
    with scripts.using_sudo():
        rootfs = parameters['//base:drydock/rootfs']
        scripts.rsync(paths, rootfs, relative=True, excludes=excludes)


def write_json_to(obj, path):
    if scripts.is_dry_run():
        return
    with scripts.ensure_path(path).open('w') as json_file:
        json_file.write(json.dumps(obj, indent=4, sort_keys=True))
        json_file.write('\n')
