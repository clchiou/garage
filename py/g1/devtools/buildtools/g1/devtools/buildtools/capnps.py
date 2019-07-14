__all__ = [
    'make_compile_schemas',
]

import subprocess
import warnings
from distutils import log
from distutils.core import Command
from pathlib import Path


def make_compile_schemas(schemas, *, import_paths=()):

    class compile_schemas(Command):

        IMPORT_PATH = ':'.join(map(str, import_paths))

        description = "compile Cap'n Proto schema files"

        user_options = [
            ('import-path=', None, 'schema file search path'),
        ]

        def initialize_options(self):
            self.import_path = self.IMPORT_PATH

        def finalize_options(self):
            pass

        def run(self):
            _compile_schemas(schemas, self.import_path.split(':'))

    return compile_schemas


def _compile_schemas(schemas, import_paths):
    """Generate the CodeGeneratorRequest."""
    schema_paths = _find_schema_paths(schemas, import_paths)
    for import_, output_path in sorted(schemas.items()):
        output_path = Path(output_path).absolute()
        if not output_path.parent.is_dir():
            cmd = ['mkdir', '--parents', str(output_path.parent)]
            subprocess.run(cmd, check=True)
        _compile(schema_paths[import_], import_paths, output_path)


def _is_absolute_import(import_):
    return import_.startswith('/')


def _find_schema_paths(imports, import_paths):
    """Find all imported Cap'n Proto schema files."""

    for import_ in imports:
        if not _is_absolute_import(import_):
            raise ValueError('all input must be absolute: %s' % import_)

    import_paths = [Path(p).absolute() for p in import_paths]
    for import_path in import_paths:
        if not import_path.is_dir():
            warnings.warn('not a directory: %s' % import_path)

    schema_paths = {}
    for import_ in imports:
        if import_ not in schema_paths:
            schema_paths[import_] = _find_import_path(import_paths, import_)

    return schema_paths


def _find_import_path(import_paths, import_):
    assert _is_absolute_import(import_)
    found = []
    for import_path in import_paths:
        schema_path = _make_schema_path(import_path, import_)
        if schema_path.is_file():
            found.append(schema_path)
    if not found:
        raise FileNotFoundError('no import path for %r' % import_)
    if len(found) > 1:
        raise RuntimeError(
            'find multiple import paths for %r: %s' % (import_, found)
        )
    return found[0]


def _make_schema_path(import_path, import_):
    # import_ must be an absolute path.
    assert import_[0] == '/' and import_[1] != '/', import_
    return import_path / import_[1:]


def _compile(schema_path, import_paths, output_path):
    """Compile the schema."""
    cmd = ['capnp', 'compile', '-o-']
    for import_path in import_paths:
        cmd.append('--import-path=%s' % Path(import_path).absolute())
    cmd.append(str(schema_path))
    log.info('execute: %s > %s', ' '.join(cmd), output_path)
    with output_path.open('wb') as output:
        subprocess.run(cmd, stdout=output, check=True)
