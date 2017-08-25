"""Custom distutils commands."""

__all__ = [
    'register_subcommands',
    'add_cplusplus_suffix',
    'read_pkg_config',
    'make_bdist_zipapp',
    'make_copy_files',
    'make_fingerprint_files',
    'make_execute_commands',
]

import hashlib
import os
import os.path
import stat
import sys
import tempfile
import zipfile
from pathlib import Path
from subprocess import check_call, check_output

from collections import namedtuple
from distutils import log
from distutils import unixccompiler
from distutils.command.build import build
from distutils.core import Command
from distutils.dir_util import ensure_relative
from distutils.errors import (
    DistutilsOptionError,
    DistutilsPlatformError,
)
from distutils.file_util import copy_file


def register_subcommands(command, *subcommands):
    """This makes sub-command a required step of command."""
    command.sub_commands[0:0] = [
        (subcommand.__name__, None) for subcommand in subcommands
    ]
    return subcommands


def add_cplusplus_suffix(suffix):
    if not suffix.startswith('.'):
        raise ValueError('suffix is not started with ".": %s' % suffix)
    if suffix not in unixccompiler.UnixCCompiler.src_extensions:
        unixccompiler.UnixCCompiler.src_extensions.append(suffix)


PackageConfig = namedtuple(
    'PackageConfig',
    'include_dirs library_dirs libraries extra_compile_args',
)


def read_pkg_config(packages):
    cmd = ['pkg-config', '--cflags', '--libs']
    cmd.extend(packages)
    args = check_output(cmd).decode('ascii').split()
    pkg_config = {
        'include_dirs': [],
        'library_dirs': [],
        'libraries': [],
        'extra_compile_args': [],
    }
    for arg in args:
        if arg.startswith('-I'):
            pkg_config['include_dirs'].append(arg[len('-I'):])
        elif arg.startswith('-L'):
            pkg_config['library_dirs'].append(arg[len('-L'):])
        elif arg.startswith('-l'):
            pkg_config['libraries'].append(arg[len('-l'):])
        else:
            pkg_config['extra_compile_args'].append(arg)
    return PackageConfig(**{
        field: sorted(set(value)) for field, value in pkg_config.items()
    })


def make_bdist_zipapp(*, python='/usr/bin/env python3',
                      main_optional=False, main=None):

    class bdist_zipapp(Command):

        PYTHON = python

        MAIN = main
        MAIN_TEMPLATE = (
            '# -*- coding: utf-8 -*-\n'
            'import {module}\n'
            '{module}.{func}()\n'
        )

        description = "create a zipapp built distribution"

        user_options = [
            ('python=', None, "python interpreter to use"),
            ('main=', None, "main function of the zipapp"),
            ('output=', None, "output zipapp path"),
        ]

        def initialize_options(self):
            self.python = self.PYTHON
            self.main = self.MAIN
            self.output = None

        def finalize_options(self):
            if self.python is None:
                raise DistutilsOptionError('--python is required')
            if self.main is None and not main_optional:
                raise DistutilsOptionError('--main is required')
            if self.output is None:
                raise DistutilsOptionError('--output is required')

        def run(self):
            if self.distribution.has_ext_modules():
                raise DistutilsPlatformError(
                    'not sure if we could make zipapp with ext module')
            with tempfile.TemporaryDirectory() as build_dir:
                self._run(build_dir)

        def _run(self, build_dir):
            self.run_command('build')

            log.info('installing to %s' % build_dir)
            install = self.reinitialize_command(
                'install',
                reinit_subcommands=1,
            )
            install.root = build_dir

            # Install lib and data but ignore headers, scripts, and egg
            # info at the moment.
            if self.distribution.has_pure_modules():
                self.run_command('install_lib')
            if self.distribution.has_data_files():
                self.run_command('install_data')

            install_lib = self.distribution.get_command_obj('install_lib')
            install_dir = install_lib.install_dir

            if self.main is not None:
                main_path = os.path.join(install_dir, '__main__.py')
                module, func = self.main.rsplit(':', maxsplit=1)
                log.info('generating %s' % main_path)
                with open(main_path, 'w') as main_file:
                    main_file.write(self.MAIN_TEMPLATE.format(
                        module=module,
                        func=func,
                    ))

            def open_zip_archive(file, mode):
                # It seems that Python interpreter can only load
                # DEFLATE-compressed zip file.
                return zipfile.ZipFile(
                    file, mode=mode,
                    compression=zipfile.ZIP_DEFLATED,
                )

            def add_content(zip_archive):
                for child in Path(install_dir).rglob('*'):
                    arcname = child.relative_to(install_dir)
                    zip_archive.write(str(child), str(arcname))

            if os.path.exists(self.output):
                log.info('appending %s' % self.output)
                with open_zip_archive(self.output, 'a') as zip_archive:
                    add_content(zip_archive)
            else:
                log.info('generating %s' % self.output)
                with open(self.output, 'wb') as output_file:
                    output_file.write(b'#!%s\n' % self.python.encode('utf-8'))
                    # Call flush() to ensure that zip content is after
                    # shebang.
                    output_file.flush()
                    with open_zip_archive(output_file, 'w') as zip_archive:
                        add_content(zip_archive)

            # Do `chmod a+x`.
            mode = os.stat(self.output).st_mode
            os.chmod(self.output, stat.S_IMODE(mode) | 0o111)

    return bdist_zipapp


def _copy_files_base(filenames, src_dir, dst_dir):

    class copy_files_base(Command):

        FILENAMES = filenames
        SRC_DIR = src_dir
        DST_DIR = dst_dir

        user_options = []
        if not SRC_DIR:
            user_options.append((
                'src-dir=', None,
                "directory to copy files from",
            ))
        if not DST_DIR:
            user_options.append((
                'dst-dir=', None,
                "directory to copy files to",
            ))

        def initialize_options(self):
            self.src_dir = self.SRC_DIR
            self.dst_dir = self.DST_DIR

        def finalize_options(self):
            if self.src_dir is None:
                raise DistutilsOptionError('--src-dir is required')
            if self.dst_dir is None:
                raise DistutilsOptionError('--dst-dir is required')
            for filename in self.FILENAMES:
                src_path = os.path.join(self.src_dir, filename)
                if not os.path.exists(src_path):
                    raise DistutilsOptionError('not a file: %s' % src_path)

    return copy_files_base


def make_copy_files(
        *,
        filenames, src_dir=None, dst_dir=None,
        name=None):
    """Return a distutils Command class for copying files."""

    class copy_files(_copy_files_base(filenames, src_dir, dst_dir)):

        description = "copy files"

        def run(self):
            for filename in self.FILENAMES:
                src_path = os.path.join(self.src_dir, filename)
                dst_path = os.path.join(self.dst_dir, filename)
                copy_file(src_path, dst_path, preserve_mode=False)

    if name:
        copy_files.__name__ = name

    return copy_files


def make_fingerprint_files(
        *,
        filenames, src_dir=None, dst_dir=None,
        name=None):
    """Fingerprint files (usually for generated web asset files)."""

    class fingerprint_files(_copy_files_base(filenames, src_dir, dst_dir)):

        description = "fingerprint files"

        def run(self):
            new_filenames = set()
            # Fingerprint files.
            for filename in self.FILENAMES:
                src_path = os.path.join(self.src_dir, filename)
                src_sha1 = hashlib.sha1()
                with open(src_path, 'rb') as src_file:
                    src_sha1.update(src_file.read())
                new_filename = '%s.%s' % (filename, src_sha1.hexdigest())
                new_filenames.add(new_filename)
                dst_path = os.path.join(self.dst_dir, new_filename)
                copy_file(src_path, dst_path, preserve_mode=False)
            # Clean up other fingerprinted files in dst_dir.
            for filename in os.listdir(self.dst_dir):
                for prefix in self.FILENAMES:
                    if (filename.startswith(prefix) and
                            filename not in new_filenames):
                        path = os.path.join(self.dst_dir, filename)
                        log.info('remove %s', path)
                        os.unlink(path)
                        break

    if name:
        fingerprint_files.__name__ = name

    return fingerprint_files


def make_execute_commands(
        *,
        commands,
        name=None):
    """Execute external commands."""

    class execute_commands(Command):

        COMMANDS = commands

        description = "execute external commands"

        user_options = []

        def initialize_options(self):
            pass

        def finalize_options(self):
            pass

        def run(self):
            for command in self.COMMANDS:
                log.info('execute: %s', ' '.join(command))
                check_call(command)

    if name:
        execute_commands.__name__ = name

    return execute_commands
