"""Helpers for writing templates (not for build rules directly)."""

__all__ = [
    'parse_common_args',

    'load_inventory',

    'tapeout_filespecs',
    'tapeout_files',

    'write_json_to',

    'render_template',
    'render_template_to_path',
]

import functools
import json
import os
import tempfile

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


# Python snippet that converts YAML to JSON.
YAML_TO_JSON = (
    'import json; '
    'import sys; '
    'from ruamel.yaml import YAML; '
    'print(json.dumps(YAML(typ="safe").load(sys.stdin)))'
)


def load_inventory(parameters, inventory_path=None):
    """Load Ansible inventory file."""
    inventory_path = scripts.ensure_file(
        inventory_path or
        os.environ.get('ANSIBLE_INVENTORY')
    )
    with scripts.redirecting(input=inventory_path.read_bytes()):
        cmd = [parameters['//host/cpython:python'], '-c', YAML_TO_JSON]
        return json.loads(scripts.execute(cmd, capture_stdout=True).stdout)


def tapeout_filespecs(parameters, top_path, spec_dicts):
    """Generate and tapeout files from file spec."""
    rootfs = parameters['//base:drydock/rootfs']
    top_path = scripts.ensure_path(top_path)
    ASSERT.false(top_path.is_absolute())
    top_path = rootfs / top_path
    with scripts.using_sudo():
        scripts.mkdir(top_path)
        for spec_dict in spec_dicts:
            spec = filespecs.make_filespec(**spec_dict)
            path = top_path / spec.path
            if spec.kind == 'file':
                if spec.content is not None:
                    scripts.tee(
                        spec.content.encode(spec.content_encoding), path)
                else:
                    ASSERT.not_none(spec.content_path)
                    scripts.cp(spec.content_path, path)
            else:
                scripts.mkdir(path)
            # Ignore spec.mtime...
            if spec.mode is not None:
                scripts.execute(['chmod', '0%o' % spec.mode, path])
            if spec.owner:
                scripts.execute(['chown', spec.owner, path])
            if spec.group:
                scripts.execute(['chgrp', spec.group, path])


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


def render_template(parameters, **kwargs):
    with tempfile.NamedTemporaryFile() as output:
        output_path = scripts.ensure_path(output.name)
        render_template_to_path(parameters, output_path=output_path, **kwargs)
        return output_path.read_text()


def render_template_to_path(
        parameters, *,
        template_path,
        template_dirs=(),
        template_vars=(),
        output_path):
    """Render a template file (with Mako)."""
    cmd = [
        scripts.ensure_file(
            parameters['//host/cpython:python'],
        ),
        scripts.ensure_file(
            parameters['//base:root'] /
            'shipyard/scripts/render-template',
        ),
    ]
    for dir_path in template_dirs:
        cmd.append('--template-dir')
        cmd.append(dir_path)
    for name, value in template_vars:
        cmd.append('--template-var')
        cmd.append(name)
        cmd.append(json.dumps(value))
    cmd.append('--output')
    cmd.append(output_path)
    cmd.append(template_path)
    scripts.execute(cmd)
