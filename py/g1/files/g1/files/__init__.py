__all__ = [
    # Extensions to Path object.
    'is_empty_dir',
    'lexists',
    'remove',
    'remove_empty_dir',
]

import logging
import shutil

logging.getLogger(__name__).addHandler(logging.NullHandler())


def is_empty_dir(path):
    """True if path points to an empty directory."""
    try:
        next(path.iterdir())
    except StopIteration:
        return True
    except (FileNotFoundError, NotADirectoryError):
        return False
    else:
        return False


def lexists(path):
    """True if path points to an existing file or symlink.

    ``lexists`` differs from ``Path.exists`` when path points to a
    broken but existent symlink: The former returns true but the latter
    returns false.
    """
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    else:
        return True


def remove(path):
    """Remove a file.

    If path points to a file or a symlink, only remove the file or
    symlink.  If path points to a directory, remove the directory
    recursively.
    """
    if not lexists(path):
        pass
    elif not path.is_dir() or path.is_symlink():
        path.unlink()
    else:
        shutil.rmtree(path)


def remove_empty_dir(path):
    try:
        next(path.iterdir())
    except StopIteration:
        path.rmdir()
    except (FileNotFoundError, NotADirectoryError):
        pass
