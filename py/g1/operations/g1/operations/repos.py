"""Manage operations repository.

General design of the interface:

* Directory objects are lazy: They do not check nor load directory
  contents during __init__.  Also, __init__ should never fail (except
  OOM, but we don't handle that case).

* The ``path`` property is the path of the directory.

* The ``init`` method will populate directory contents (maybe be with
  sentinel values).  If the init call succeeds, subsequent check call
  should pass.

* The ``check`` method will check directory contents.  It is also called
  indirectly through property accesses.

* The ``cleanup`` method clears directory contents (you cannot simply
  remove the directory as an ops dir might require custom steps to clear
  its contents).  The directory might be partially cleaned up, and
  cleanup should handle such cases.  If the cleanup call succeeds, you
  may remove the directory.  You should not call cleanup when an ops dir
  is still active.

* The ``check_invariants`` method checks invariance among all active
  operations directories.

* The ``activate`` and ``deactivate`` method changes an ops dir to
  active/inactive state.

* The ``install`` and ``uninstall`` method should return false if the
  call skips the install/uninstall step.
"""

__all__ = [
    'BundleDirInterface',
    'OpsDirInterface',
    'OpsDirs',
]

import contextlib
import logging
import random
import tempfile
from pathlib import Path

from g1.bases import classes
from g1.bases.assertions import ASSERT
from g1.files import locks

from . import bases

LOG = logging.getLogger(__name__)

# Top-level directories.
_ACTIVE = 'active'
_GRAVEYARD = 'graveyard'
_TMP = 'tmp'


class BundleDirInterface:

    path_unchecked = classes.abstract_property

    check = classes.abstract_method

    install = classes.abstract_method
    uninstall = classes.abstract_method

    name = classes.abstract_property
    version = classes.abstract_property

    __repr__ = classes.make_repr('path={self.path_unchecked}')

    def __eq__(self, other):
        return self.path_unchecked == other.path_unchecked

    def __hash__(self):
        return hash(self.path_unchecked)

    @classes.memorizing_property
    def path(self):
        self.check()
        return self.path_unchecked


class OpsDirInterface:

    path_unchecked = classes.abstract_property

    init = classes.abstract_method
    check = classes.abstract_method
    cleanup = classes.abstract_method

    check_invariants = classes.abstract_method

    get_ops_dir_name = classes.abstract_method

    init_from_bundle_dir = classes.abstract_method
    activate = classes.abstract_method
    deactivate = classes.abstract_method
    uninstall = classes.abstract_method

    __repr__ = classes.make_repr('path={self.path_unchecked}')

    def __eq__(self, other):
        return self.path_unchecked == other.path_unchecked

    def __hash__(self):
        return hash(self.path_unchecked)

    @classes.memorizing_property
    def path(self):
        self.check()
        return self.path_unchecked

    def remove(self):
        # Just a sanity check.  An ops dir under the active directory
        # could be in active state, and so we should not remove it.
        ASSERT.not_equal(self.path_unchecked.parent.name, _ACTIVE)
        self.cleanup()
        self.path.rmdir()  # pylint: disable=no-member


class OpsDirs:
    """Manage collection of operations directories.

    For now our locking strategy is very naive: We simply lock the
    top-level directory that we are using.  We will revisit this
    strategy if this causes a lot of lock contention.

    NOTE: When locking multiple top-level directories, lock them in
    alphabetical order to avoid deadlock.
    """

    def __init__(
        self,
        kind,
        path,
        *,
        bundle_dir_type,
        ops_dir_type,
    ):
        self.kind = kind
        self.path_unchecked = path
        self.bundle_dir_type = bundle_dir_type
        self.ops_dir_type = ops_dir_type

    __repr__ = classes.make_repr('path={self.path_unchecked}')

    def __eq__(self, other):
        return self.path_unchecked == other.path_unchecked

    def __hash__(self):
        return hash(self.path_unchecked)

    def init(self):
        bases.make_dir(self.path_unchecked)
        bases.make_dir(self.path_unchecked / _ACTIVE)
        bases.make_dir(self.path_unchecked / _GRAVEYARD)
        bases.make_dir(self.path_unchecked / _TMP)

    def check(self):
        ASSERT.predicate(self.path_unchecked, Path.is_dir)
        ASSERT.predicate(self.path_unchecked / _ACTIVE, Path.is_dir)
        ASSERT.predicate(self.path_unchecked / _GRAVEYARD, Path.is_dir)
        ASSERT.predicate(self.path_unchecked / _TMP, Path.is_dir)

    @classes.memorizing_property
    def path(self):
        self.check()
        return self.path_unchecked

    @classes.memorizing_property
    def active_dir_path(self):
        return self.path / _ACTIVE

    @classes.memorizing_property
    def graveyard_dir_path(self):
        return self.path / _GRAVEYARD

    @classes.memorizing_property
    def tmp_dir_path(self):
        return self.path / _TMP

    def _get_ops_dir_path(self, name, version):
        return (
            self.active_dir_path / \
            self.ops_dir_type.get_ops_dir_name(name, version)
        )

    @contextlib.contextmanager
    def listing_ops_dirs(self):
        """Return a list of ops dir objects.

        NOTE: This only locks the active dir, and does NOT locks each
        ops dir.
        """
        with locks.acquiring_shared(self.active_dir_path):
            yield self._list_ops_dirs()

    def _list_ops_dirs(self):
        ops_dirs = []
        for ops_dir_path in (
            self.active_dir_path.iterdir()  # pylint: disable=no-member
        ):
            if not ops_dir_path.is_dir():
                LOG.debug(
                    '%s: unknown file under active: %s',
                    self.kind,
                    ops_dir_path,
                )
                continue
            ops_dirs.append(self.ops_dir_type(ops_dir_path))
        return ops_dirs

    @contextlib.contextmanager
    def using_ops_dir(self, name, version):
        ops_dir_path = self._get_ops_dir_path(name, version)
        with locks.acquiring_shared(self.active_dir_path):
            ops_dir_lock = self._try_lock_ops_dir(ops_dir_path)
        if not ops_dir_lock:
            yield None
            return
        try:
            yield self.ops_dir_type(ops_dir_path)
        finally:
            ops_dir_lock.release()
            ops_dir_lock.close()

    def install(self, bundle_dir):
        """Install bundle."""
        log_args = (self.kind, bundle_dir.name, bundle_dir.version)
        ops_dir_path = self._get_ops_dir_path(
            bundle_dir.name, bundle_dir.version
        )
        if ops_dir_path.exists():
            LOG.info('skip: %s install: %s %s', *log_args)
            return False
        tmp_ops_dir = self._make_tmp_ops_dir()
        try:
            tmp_ops_dir.init_from_bundle_dir(bundle_dir)
            with locks.acquiring_exclusive(self.active_dir_path):
                if ops_dir_path.exists():
                    LOG.info('skip: %s install: %s %s', *log_args)
                    return False
                LOG.info('%s install: %s %s', *log_args)
                tmp_ops_dir.check_invariants(self._list_ops_dirs())
                try:
                    bundle_dir.install()
                except:
                    if not bundle_dir.uninstall():
                        LOG.error('%s: unable to rollback: %s %s', *log_args)
                    raise
                tmp_ops_dir.path.rename(ops_dir_path)
                tmp_ops_dir = None
        finally:
            if tmp_ops_dir:
                tmp_ops_dir.remove()
        return True

    def _make_tmp_ops_dir(self):
        with locks.acquiring_exclusive(self.tmp_dir_path):
            tmp_ops_dir = self.ops_dir_type(
                Path(tempfile.mkdtemp(dir=self.tmp_dir_path))
            )
            try:
                tmp_ops_dir.init()
            except:
                tmp_ops_dir.remove()
                raise
            return tmp_ops_dir

    def uninstall(self, name, version):
        log_args = (self.kind, name, version)
        ops_dir_path = self._get_ops_dir_path(name, version)
        with locks.acquiring_exclusive(self.active_dir_path):
            ops_dir_lock = self._try_lock_ops_dir(ops_dir_path)
            if not ops_dir_lock:
                LOG.info('skip: %s uninstall: %s %s', *log_args)
                return False
        LOG.info('%s uninstall: %s %s', *log_args)
        try:
            ops_dir = self.ops_dir_type(ops_dir_path)
            ops_dir.deactivate()
            ops_dir.uninstall()
            self.ops_dir_type(self._move_to_graveyard(ops_dir_path)).remove()
        finally:
            ops_dir_lock.release()
            ops_dir_lock.close()
        return True

    def _move_to_graveyard(self, ops_dir_path):
        with locks.acquiring_exclusive(self.graveyard_dir_path):
            grave_path = self._make_grave_path(ops_dir_path.name)
            ops_dir_path.rename(grave_path)
        return grave_path

    def _make_grave_path(self, ops_dir_name):
        grave_path = self.graveyard_dir_path / ops_dir_name
        if not grave_path.exists():
            return grave_path
        for _ in range(3):
            grave_path = (
                self.graveyard_dir_path / \
                ('%s.%08d' % (ops_dir_name, random.randint(0, 1e8)))
            )
            if not grave_path.exists():
                return grave_path
        return ASSERT.unreachable('unable to generate unique grave path')

    def cleanup(self):
        for top_dir_path in (self.tmp_dir_path, self.graveyard_dir_path):
            with locks.acquiring_exclusive(top_dir_path):
                self._cleanup_top_dir(top_dir_path)

    def _cleanup_top_dir(self, top_dir_path):
        for ops_dir_path in top_dir_path.iterdir():
            log_args = (self.kind, ops_dir_path)
            if not ops_dir_path.is_dir():
                LOG.warning('%s cleanup: %s; reason: unknown file', *log_args)
                ops_dir_path.unlink()
                continue
            ops_dir_lock = self._try_lock_ops_dir(ops_dir_path)
            if not ops_dir_lock:
                LOG.info('skip: %s cleanup: %s', *log_args)
                continue
            try:
                LOG.info('%s cleanup: %s', *log_args)
                self.ops_dir_type(ops_dir_path).remove()
            finally:
                ops_dir_lock.release()
                ops_dir_lock.close()

    def _try_lock_ops_dir(self, ops_dir_path):
        """Try to lock an ops dir exclusively.

        NOTE: Caller is required to lock the active dir.
        """
        log_args = (self.kind, ops_dir_path)
        if not ops_dir_path.exists():
            LOG.debug('%s: cannot lock: no such directory: %s', *log_args)
            return None
        if not ops_dir_path.is_dir():
            LOG.debug('%s: cannot lock: not a directory: %s', *log_args)
            return None
        ops_dir_lock = locks.try_acquire_exclusive(ops_dir_path)
        if not ops_dir_lock:
            LOG.debug('%s: cannot lock: locked by other: %s', *log_args)
            return None
        return ops_dir_lock
