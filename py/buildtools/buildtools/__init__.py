"""Custom distutils commands."""

__all__ = [
    'register_subcommands',
    'make_copy_files',
    'make_fingerprint_files',
]

import hashlib
import os
import os.path
from distutils import log
from distutils.command.build import build
from distutils.core import Command
from distutils.errors import DistutilsOptionError
from distutils.file_util import copy_file


def register_subcommands(command, *subcommands):
    """This makes sub-command a required step of command."""
    command.sub_commands[0:0] = [
        (subcommand.__name__, None) for subcommand in subcommands
    ]


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


def make_copy_files(*, filenames, src_dir=None, dst_dir=None):
    """Return a distutils Command class for copying files."""

    class copy_files(_copy_files_base(filenames, src_dir, dst_dir)):

        description = "copy files"

        def run(self):
            for filename in self.FILENAMES:
                src_path = os.path.join(self.src_dir, filename)
                dst_path = os.path.join(self.dst_dir, filename)
                copy_file(src_path, dst_path, preserve_mode=False)

    return copy_files


def make_fingerprint_files(*, filenames, src_dir=None, dst_dir=None):
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

    return fingerprint_files
