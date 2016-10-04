"""Helpers for building Cap'n Proto schema files."""

__all__ = [
    'find_schemas',
    'make_compile_command',
    'make_path',
]

import warnings
from collections import OrderedDict, namedtuple
from pathlib import Path
from subprocess import check_output

from .schema import CodeGeneratorRequest


Schema = namedtuple('Schema', [
    'import_',
    'import_path',
    'path',
    'dependencies',
])


# Hard code standard imports that we should not follow recursively when
# finding schemas.
STANDARD_IMPORTS = frozenset((
    '/capnp/c++.capnp',
    '/capnp/json.capnp',
    '/capnp/persistent.capnp',
    '/capnp/rpc.capnp',
    '/capnp/rpc-twoparty.capnp',
    '/capnp/schema.capnp',
))


def find_schemas(imports, import_paths):
    """Find all imported Cap'n Proto schema files."""

    for import_ in imports:
        if not _is_absolute_import(import_):
            raise ValueError('all input must be absolute: %s' % import_)

    import_paths = [Path(p).absolute() for p in import_paths]
    for import_path in import_paths:
        if not import_path.is_dir():
            warnings.warn('not a directory: %s' % import_path)

    schemas = OrderedDict()

    queue = list(imports)
    while queue:

        import_ = queue.pop(0)
        if import_ in schemas or import_ in STANDARD_IMPORTS:
            continue

        import_path, schema_path = _find_import_path(import_paths, import_)
        request = _parse_schema_file(import_path, schema_path, import_paths)

        dependencies = []
        for requested_file in request.requested_files:
            for dependency in requested_file.imports:
                dep_import = dependency.name
                if not _is_absolute_import(dep_import):
                    dep_import = Path(import_).parent / dep_import
                    dep_import = str(dep_import.absolute())
                assert _is_absolute_import(dep_import)
                dependencies.append(dep_import)
                queue.append(dep_import)

        schemas[import_] = Schema(
            import_=import_,
            import_path=import_path,
            path=_make_schema_path(import_path, import_),
            dependencies=tuple(dependencies),
        )

    return schemas


def make_compile_command(schema, import_paths, language, output_dir=None):
    """Return a shell command compiling the schema."""
    cmd = ['capnp', 'compile']
    for import_path in import_paths:
        cmd.append('--import-path=%s' % Path(import_path).absolute())
    cmd.append('--src-prefix=%s' % schema.import_path)
    if output_dir:
        cmd.append('--output=%s:%s' % (language, output_dir))
    else:
        cmd.append('--output=%s' % language)
    cmd.append(str(schema.path))
    return cmd


def make_path(dir_path, schema, with_added_suffix=None):
    assert schema.import_[0] == '/' and schema.import_[1] != '/'
    path = Path(dir_path) / schema.import_[1:]
    if with_added_suffix:
        if not with_added_suffix.startswith('.'):
            raise ValueError(
                'suffix is not started with ".": %s' % with_added_suffix)
        path = path.with_name(path.name + with_added_suffix)
    return path


def _is_absolute_import(import_):
    return import_.startswith('/')


def _find_import_path(import_paths, import_):
    assert _is_absolute_import(import_)
    found = []
    for import_path in import_paths:
        schema_path = _make_schema_path(import_path, import_)
        if schema_path.is_file():
            found.append((import_path, schema_path))
    if not found:
        raise FileNotFoundError('no import path for %r' % import_)
    if len(found) > 1:
        raise RuntimeError(
            'find multiple import paths for %r: %s' % (import_, found))
    return found[0]


def _make_schema_path(import_path, import_):
    assert import_[0] == '/' and import_[1] != '/'
    return import_path / import_[1:]


def _parse_schema_file(import_path, schema_path, import_paths):
    cmd = ['capnp', 'compile']
    for path in import_paths:
        cmd.append('--import-path=%s' % path)
    cmd.append('--src-prefix=%s' % import_path)
    cmd.append('--output=-')
    cmd.append(str(schema_path))
    return CodeGeneratorRequest(check_output(cmd))
