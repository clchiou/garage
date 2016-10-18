"""Helpers for building Cap'n Proto schema files."""

__all__ = [
    'compile_schemas',
    'make_post_cythonize_fix',
]

import os
import re
import warnings
from collections import OrderedDict, namedtuple
from distutils import log
from distutils.core import Command
from pathlib import Path
from subprocess import check_call, check_output

import buildtools

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


def compile_schemas(imports, output_dir):

    # capnp generates files with .c++ suffix.
    buildtools.add_cplusplus_suffix('.c++')

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
    import_paths = os.environ.get('PYTHONPATH', [])
    if import_paths:
        import_paths = import_paths.split(':')
    schemas = _find_schemas(imports, import_paths)

    if not Path(output_dir).is_dir():
        _execute(['mkdir', '--parents', output_dir])

    # Run `capnp compile` before Cython runs.
    sources = []
    for schema in schemas.values():
        output_path = _make_path(output_dir, schema, '.c++')
        if (not output_path.is_file() or
                _mtime_lt(output_path, schema.import_path)):
            _compile(schema, import_paths, 'c++', output_dir)
        sources.append(str(output_path))
    for import_ in imports:
        schema = schemas[import_]
        # capnpc-pyx generates "schema.pyx", not "schema.capnp.pyx".
        output_path = _make_path(output_dir, schema).with_suffix('.pyx')
        if (not output_path.is_file() or
                _mtime_lt(output_path, schema.import_path)):
            _compile(schema, import_paths, 'pyx', output_dir)
        sources.append(str(output_path))

    return sources


def _mtime_lt(path1, path2):
    return path1.lstat().st_mtime < path2.lstat().st_mtime


def _find_schemas(imports, import_paths):
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


def _compile(schema, import_paths, language, output_dir=None):
    """Compile the schema."""
    cmd = ['capnp', 'compile']
    for import_path in import_paths:
        cmd.append('--import-path=%s' % Path(import_path).absolute())
    cmd.append('--src-prefix=%s' % schema.import_path)
    if output_dir:
        cmd.append('--output=%s:%s' % (language, output_dir))
    else:
        cmd.append('--output=%s' % language)
    cmd.append(str(schema.path))
    _execute(cmd)


def _execute(cmd):
    # Use print() rather than distutils.log.info() because this is
    # called before log is configured.
    print('execute: %s' % ' '.join(cmd))
    check_call(cmd)


def _make_path(dir_path, schema, with_added_suffix=None):
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


def make_post_cythonize_fix(cpp_src_paths):
    """Fix generated .cpp files (we need this fix to workaround Cython's
       limitation that it cannot allocate C++ object on stack if it does
       not have default constructor).
    """

    class post_cythonize_fix(Command):

        CPP_SRC_PATHS = list(map(Path, cpp_src_paths))

        PATTERN_CONS = re.compile(
            r'([a-zA-Z0-9_]+(?:::[a-zA-Z0-9_]+)*::Builder)\(\);')

        PATTERN_VAR = re.compile(
            r'([a-zA-Z0-9_]+(?:::[a-zA-Z0-9_]+)*::Builder)(\s+__pyx_[a-zA-Z0-9_]+);')

        description = "apply post-cythonize fix"

        user_options = []

        def initialize_options(self):
            pass

        def finalize_options(self):
            pass

        def run(self):
            for cpp_src_path in self.CPP_SRC_PATHS:
                log.info('apply post-Cythonize fix to: %s', cpp_src_path)
                orig_path = cpp_src_path.with_name(cpp_src_path.name + '.orig')
                cpp_src_path.rename(orig_path)
                with orig_path.open('r') as cpp_src:
                    with cpp_src_path.open('w') as output:
                        for line in cpp_src:
                            output.write(self._post_cythonize_fix(line))

        def _post_cythonize_fix(self, line):

            match = self.PATTERN_CONS.search(line)
            if match:
                type_ = match.group(1)
                if not type_.startswith('capnp'):
                    return '%s%s(nullptr);%s' % (
                        line[:match.start()],
                        type_,
                        line[match.end():],
                    )

            match = self.PATTERN_VAR.search(line)
            if match:
                type_ = match.group(1)
                if not type_.startswith('capnp'):
                    return '%s%s%s(nullptr);%s' % (
                        line[:match.start()],
                        type_,
                        match.group(2),
                        line[match.end():],
                    )

            return line

    return post_cythonize_fix
