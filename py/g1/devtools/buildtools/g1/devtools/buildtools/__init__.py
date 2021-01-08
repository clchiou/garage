__all__ = [
    'make_bdist_zipapp',
    'make_copy_files',
    'read_package_config',
    'register_subcommands',
]

import collections
import distutils.core
import distutils.errors
import distutils.file_util
import os.path
import shlex
import subprocess

# Re-export.
from .zipapps import make_bdist_zipapp


def register_subcommands(command, *subcommands):
    """Make sub-commands as a required step of ``command``."""
    command.sub_commands[0:0] = [(subcommand.__name__, None)
                                 for subcommand in subcommands]
    return subcommands


def make_copy_files(*, filenames, src_dir=None, dst_dir=None):

    class copy_files(distutils.core.Command):

        FILENAMES = filenames
        SRC_DIR = src_dir
        DST_DIR = dst_dir

        description = "copy files from one directory to another"

        user_options = [
            *(() if SRC_DIR else
              (('src-dir=', None, "directory to copy files from"), )),
            *(() if DST_DIR else
              (('dst-dir=', None, "directory to copy files to"), )),
        ]

        def initialize_options(self):
            self.src_dir = self.SRC_DIR
            self.dst_dir = self.DST_DIR

        def finalize_options(self):
            if self.src_dir is None:
                raise distutils.errors.DistutilsOptionError(
                    '--src-dir is required'
                )
            if self.dst_dir is None:
                raise distutils.errors.DistutilsOptionError(
                    '--dst-dir is required'
                )
            for filename in self.FILENAMES:
                src_path = os.path.join(self.src_dir, filename)
                if not os.path.exists(src_path):
                    raise distutils.errors.DistutilsOptionError(
                        'source file does not exist: %s' % src_path
                    )

        def run(self):
            for filename in self.FILENAMES:
                distutils.file_util.copy_file(
                    os.path.join(self.src_dir, filename),
                    os.path.join(self.dst_dir, filename),
                    preserve_mode=False,
                )

    return copy_files


PackageConfig = collections.namedtuple(
    'PackageConfig',
    'include_dirs library_dirs libraries extra_compile_args',
)


def read_package_config(packages):
    cmd = ['pkg-config', '--cflags', '--libs']
    cmd.extend(packages)
    args = (
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE) \
        .stdout
        .decode('utf-8')
    )
    args = shlex.split(args)
    config = {
        'include_dirs': [],
        'library_dirs': [],
        'libraries': [],
        'extra_compile_args': [],
    }
    for arg in args:
        if arg.startswith('-I'):
            config['include_dirs'].append(arg[len('-I'):])
        elif arg.startswith('-L'):
            config['library_dirs'].append(arg[len('-L'):])
        elif arg.startswith('-l'):
            config['libraries'].append(arg[len('-l'):])
        else:
            config['extra_compile_args'].append(arg)
    return PackageConfig(
        **{
            # Use list instead of tuple (``sorted`` returns list) since
            # ``setuptools.extension.Extension`` only accepts list.
            field: sorted(set(value))
            for field, value in config.items()
        }
    )
