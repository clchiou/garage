"""Custom distutils commands."""

__all__ = [
    'register_subcommand',
    'make_copy_files',
]

import os.path
from distutils.command.build import build
from distutils.core import Command
from distutils.errors import DistutilsOptionError
from distutils.file_util import copy_file


def register_subcommand(command, subcommand):
    """This makes sub-command a required step of command."""
    command.sub_commands.insert(0, (subcommand.__name__, None))


def make_copy_files(*, filenames, src_dir=None, dst_dir=None):
    """Return a distutils Command class for copying files."""

    class copy_files(Command):

        FILENAMES = filenames
        SRC_DIR = src_dir
        DST_DIR = dst_dir

        description = "copy files"

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

        def run(self):
            for filename in self.FILENAMES:
                src_path = os.path.join(self.src_dir, filename)
                dst_path = os.path.join(self.dst_dir, filename)
                copy_file(src_path, dst_path, preserve_mode=False)

    return copy_files
