__all__ = [
    'make_compile_schemas',
]

import os
import warnings
from distutils import log
from distutils.core import Command
from pathlib import Path
from subprocess import check_call


def make_compile_schemas(schemas, *, import_paths=None):

    class compile_schemas(Command):

        description = "compile Cap'n Proto schema files"

        def initialize_options(self):
            pass

        def finalize_options(self):
            pass

        def run(self):
            _compile_schemas(schemas, import_paths)

    return compile_schemas


def _compile_schemas(schemas, import_paths):
    """Generate the CodeGeneratorRequest."""

    import_paths = import_paths or []

    #
    # Unfortunately setup.py does not have a nice way to pass import
    # paths to us in all scenarios.
    #
    # * Adding new command-line arguments (e.g., --capnp-import-path)
    #   would not be recognized by distutils (unless you remove them
    #   before distutils starts parsing command-line arguments).
    #
    # * Using existing command-line arguments (like --include-dirs) does
    #   not work because you do not always invoke the associated command
    #   (which is build_ext in this case).
    #
    # * Adding new environment variable (e.g., CAPNP_IMPORT_PATH) does
    #   not work because sudo does not preserve non-whitelisted
    #   environment variables.  This problem arises when you run:
    #
    #       sudo python setup.py install
    #
    # Which leaves us to the only option to use PYTHONPATH for passing
    # import paths.  This works with sudo because my build tools
    # explicitly make sudo preserve PYTHONPATH.
    #
    pythonpath = os.environ.get('PYTHONPATH')
    if pythonpath:
        import_paths.extend(pythonpath.split(':'))

    schema_paths = _find_schema_paths(schemas, import_paths)

    for import_, output_path in sorted(schemas.items()):

        output_path = Path(output_path).absolute()
        if not output_path.parent.is_dir():
            check_call(['mkdir', '--parents', str(output_path.parent)])

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
            'find multiple import paths for %r: %s' % (import_, found))
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
        check_call(cmd, stdout=output)
