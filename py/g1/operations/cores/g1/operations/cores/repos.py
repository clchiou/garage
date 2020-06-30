"""Manage operations repository.

General design of the interface:

* The ``path`` property is the path of the directory.

* The ``check_invariants`` method checks invariants among all active
  operations directories.

* The ``install`` and ``uninstall`` method should return false if the
  call skips the install/uninstall step.

* The ``uninstall`` method clears directory content (you cannot simply
  remove the directory as an ops dir might require custom steps to
  uninstall stuff).  The directory might be partially uninstalled, and
  uninstall method should handle such cases.  If the uninstall call
  succeeds, the directory should be empty.

* You should not call uninstall when an ops dir is still active.

* The ``start`` and ``stop`` method changes an ops dir to active or
  inactive state.
"""

__all__ = [
    'AbstractBundleDir',
    'AbstractOpsDir',
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
from g1.texts import jsons

from . import bases
from . import models

LOG = logging.getLogger(__name__)

# Top-level directories.
_ACTIVE = 'active'
_GRAVEYARD = 'graveyard'
_TMP = 'tmp'


class AbstractBundleDir:

    deploy_instruction_type = classes.abstract_property

    post_init = classes.abstract_method

    def __init__(self, path):
        self.path = path
        self.deploy_instruction = jsons.load_dataobject(
            self.deploy_instruction_type,
            ASSERT.predicate(self.deploy_instruction_path, Path.is_file)
        )
        self.post_init()

    __repr__ = classes.make_repr('path={self.path}')

    def __eq__(self, other):
        return self.path == other.path

    def __hash__(self):
        return hash(self.path)

    @property
    def deploy_instruction_path(self):
        return self.path / models.BUNDLE_DEPLOY_INSTRUCTION_FILENAME

    @property
    def label(self):
        return self.deploy_instruction.label

    @property
    def version(self):
        return self.deploy_instruction.version


class AbstractOpsDir:

    metadata_type = classes.abstract_property

    check_invariants = classes.abstract_method
    install = classes.abstract_method
    start = classes.abstract_method
    stop = classes.abstract_method
    uninstall = classes.abstract_method

    def __init__(self, path):
        self.path = path

    __repr__ = classes.make_repr('path={self.path}')

    def __eq__(self, other):
        return self.path == other.path

    def __hash__(self):
        return hash(self.path)

    @property
    def metadata_path(self):
        return self.path / models.OPS_DIR_METADATA_FILENAME

    # XXX: This annotation works around pylint no-member false errors.
    metadata: object

    @classes.memorizing_property
    def metadata(self):  # pylint: disable=function-redefined
        return jsons.load_dataobject(
            self.metadata_type,
            ASSERT.predicate(self.metadata_path, Path.is_file),
        )

    @property
    def label(self):
        return self.metadata.label

    @property
    def version(self):
        return self.metadata.version

    @property
    def refs_dir_path(self):
        return self.path / models.OPS_DIR_REFS_DIR_NAME

    @property
    def volumes_dir_path(self):
        return self.path / models.OPS_DIR_VOLUMES_DIR_NAME


class OpsDirs:
    """Manage collection of operations directories.

    For now our locking strategy is very naive: We simply lock the
    top-level directory that we are using.  We will revisit this
    strategy if this causes a lot of lock contention.

    NOTE: When locking multiple top-level directories, lock them in
    alphabetical order to avoid deadlock.
    """

    @staticmethod
    def init(path):
        bases.make_dir(path)
        bases.make_dir(path / _ACTIVE)
        bases.make_dir(path / _GRAVEYARD)
        bases.make_dir(path / _TMP)

    def post_init(self):
        ASSERT.predicate(self.path, Path.is_dir)
        ASSERT.predicate(self.active_dir_path, Path.is_dir)
        ASSERT.predicate(self.graveyard_dir_path, Path.is_dir)
        ASSERT.predicate(self.tmp_dir_path, Path.is_dir)

    def __init__(
        self,
        kind,
        path,
        *,
        bundle_dir_type,
        ops_dir_type,
    ):
        self.kind = kind
        self.path = path
        self.bundle_dir_type = bundle_dir_type
        self.ops_dir_type = ops_dir_type
        self.post_init()

    __repr__ = classes.make_repr('path={self.path}')

    def __eq__(self, other):
        return self.path == other.path

    def __hash__(self):
        return hash(self.path)

    @property
    def active_dir_path(self):
        return self.path / _ACTIVE

    @property
    def graveyard_dir_path(self):
        return self.path / _GRAVEYARD

    @classes.memorizing_property
    def tmp_dir_path(self):
        return self.path / _TMP

    def _get_ops_dir_path(self, label, version):
        # Underscore '_' is not a validate character of label path and
        # version for now; so it should be safe to join them with it.
        return (
            self.active_dir_path / \
            (
                '%s__%s' % (
                    label[2:].replace('/', '_').replace(':', '__'),
                    version,
                )
            )
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
        for ops_dir_path in self.active_dir_path.iterdir():
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
    def using_ops_dir(self, label, version):
        ops_dir_path = self._get_ops_dir_path(label, version)
        with locks.acquiring_shared(self.active_dir_path):
            ASSERT.predicate(ops_dir_path, Path.is_dir)
            ops_dir_lock = locks.acquire_exclusive(ops_dir_path)
        try:
            yield self.ops_dir_type(ops_dir_path)
        finally:
            ops_dir_lock.release()
            ops_dir_lock.close()

    def install(self, bundle_dir_path):
        """Install bundle.

        * While we try to roll back on error, it does not mean that
          install is transactional.  On the contrary, it is very hard to
          make it transactional because install involves copying,
          moving, and changing a lot of files.
        * Roll back could fail and leave partial states in the system.
          You may run cleanup, which will try to remove these partial
          states.
        """
        bundle_dir = self.bundle_dir_type(bundle_dir_path)
        log_args = (self.kind, bundle_dir.label, bundle_dir.version)
        target_ops_dir_path = self._get_ops_dir_path(
            bundle_dir.label, bundle_dir.version
        )
        if target_ops_dir_path.exists():
            LOG.info('skip: %s install: %s %s', *log_args)
            return False
        ops_dir_path = ops_dir_lock = ops_dir = None
        try:
            LOG.info('%s install: prepare: %s %s', *log_args)
            with locks.acquiring_exclusive(self.tmp_dir_path):
                ops_dir_path = Path(tempfile.mkdtemp(dir=self.tmp_dir_path))
                ops_dir_lock = locks.acquire_exclusive(ops_dir_path)
            bases.set_dir_attrs(ops_dir_path)
            ops_dir = self.ops_dir_type(ops_dir_path)
            ops_dir.install(bundle_dir, target_ops_dir_path)
            with locks.acquiring_exclusive(self.active_dir_path):
                if target_ops_dir_path.exists():
                    LOG.info('skip: %s install: %s %s', *log_args)
                    return False
                LOG.info('%s install: commit: %s %s', *log_args)
                ops_dir.check_invariants(self._list_ops_dirs())
                ops_dir_path.rename(target_ops_dir_path)
                ops_dir_path = ops_dir = None
        finally:
            if ops_dir:
                ops_dir.uninstall()
            if ops_dir_path:
                ops_dir_path.rmdir()
            if ops_dir_lock:
                ops_dir_lock.release()
                ops_dir_lock.close()
        return True

    def uninstall(self, label, version):
        log_args = (self.kind, label, version)
        ops_dir_path = self._get_ops_dir_path(label, version)
        with locks.acquiring_exclusive(self.active_dir_path):
            if not ops_dir_path.is_dir():
                LOG.info('skip: %s uninstall: %s %s', *log_args)
                return False
            ops_dir_lock = locks.acquire_exclusive(ops_dir_path)
        try:
            LOG.info('%s uninstall: %s %s', *log_args)
            self.ops_dir_type(ops_dir_path).stop()
            self._remove_ops_dir(self._move_to_graveyard(ops_dir_path))
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
            ops_dir_lock = locks.try_acquire_exclusive(ops_dir_path)
            if not ops_dir_lock:
                LOG.info('skip: %s cleanup: %s', *log_args)
                continue
            try:
                LOG.info('%s cleanup: %s', *log_args)
                self._remove_ops_dir(ops_dir_path)
            finally:
                ops_dir_lock.release()
                ops_dir_lock.close()

    def _remove_ops_dir(self, ops_dir_path):
        # Just a sanity check.  An ops dir under the active directory
        # could be in active state, and so we should not remove it.
        ASSERT.not_equal(ops_dir_path.parent.name, _ACTIVE)
        ops_dir = self.ops_dir_type(ops_dir_path)
        ops_dir.uninstall()
        ops_dir.path.rmdir()
