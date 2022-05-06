__all__ = [
    'init',
    'make_ops_dirs',
]

import logging
from pathlib import Path

import g1.files
from g1.bases.assertions import ASSERT
from g1.containers import scripts as ctr_scripts
from g1.texts import jsons

from . import bases
from . import models
from . import repos

LOG = logging.getLogger(__name__)


class XarBundleDir(repos.AbstractBundleDir):

    deploy_instruction_type = models.XarDeployInstruction

    def post_init(self):
        ASSERT.predicate(self.path, Path.is_dir)
        ASSERT.predicate(self.deploy_instruction_path, Path.is_file)
        if self.deploy_instruction.is_zipapp():
            ASSERT.predicate(self.zipapp_path, Path.is_file)
        else:
            ASSERT.predicate(self.image_path, Path.is_file)

    @property
    def zipapp_path(self):
        ASSERT.true(self.deploy_instruction.is_zipapp())
        return self.path / models.XAR_BUNDLE_ZIPAPP_FILENAME

    @property
    def image_path(self):
        ASSERT.false(self.deploy_instruction.is_zipapp())
        return self.path / models.XAR_BUNDLE_IMAGE_FILENAME


class XarOpsDir(repos.AbstractOpsDir):

    metadata_type = models.XarMetadata
    # XXX: This annotation works around pylint no-member false errors.
    metadata: object

    @property
    def zipapp_target_path(self):
        ASSERT.true(self.metadata.is_zipapp())
        return bases.get_zipapp_target_path(self.metadata.name)

    def check_invariants(self, active_ops_dirs):
        for ops_dir in active_ops_dirs:
            ASSERT(
                ops_dir.metadata.name != self.metadata.name,
                'expect unique xar label name: {}, {}',
                ops_dir.label,
                self.label,
            )

    def install(self, bundle_dir, target_ops_dir_path):
        del target_ops_dir_path  # Unused.
        ASSERT.isinstance(bundle_dir, XarBundleDir)
        log_args = (bundle_dir.label, bundle_dir.version)

        # Make metadata first so that uninstall may roll back properly.
        LOG.info('xars install: metadata: %s %s', *log_args)
        jsons.dump_dataobject(
            models.XarMetadata(
                label=bundle_dir.label,
                version=bundle_dir.version,
                image=bundle_dir.deploy_instruction.image,
            ),
            self.metadata_path,
        )
        bases.set_file_attrs(self.metadata_path)
        # Sanity check of the just-written metadata file.
        ASSERT.equal(self.label, bundle_dir.label)
        ASSERT.equal(self.version, bundle_dir.version)

        if bundle_dir.deploy_instruction.is_zipapp():
            LOG.info('xars install: zipapp: %s %s', *log_args)
            bases.copy_exec(bundle_dir.zipapp_path, self.zipapp_target_path)
        else:
            LOG.info('xars install: xar: %s %s', *log_args)
            ctr_scripts.ctr_import_image(bundle_dir.image_path)
            ctr_scripts.ctr_install_xar(
                bundle_dir.deploy_instruction.name,
                bundle_dir.deploy_instruction.exec_relpath,
                bundle_dir.deploy_instruction.image,
            )

        return True

    def start(self):
        pass  # Nothing here.

    def stop(self):
        pass  # Nothing here.

    def stop_all(self):
        pass  # Nothing here.

    def uninstall(self):
        if not self.metadata_path.exists():
            LOG.info('skip: xars uninstall: metadata was removed')
            ASSERT.predicate(self.path, g1.files.is_empty_dir)
            return False
        log_args = (self.label, self.version)
        if self.metadata.is_zipapp():
            LOG.info('xars uninstall: zipapp: %s %s', *log_args)
            g1.files.remove(self.zipapp_target_path)
        else:
            LOG.info('xars uninstall: xar: %s %s', *log_args)
            ctr_scripts.ctr_uninstall_xar(self.metadata.name)
            ctr_scripts.ctr_remove_image(self.metadata.image)
        g1.files.remove(self.metadata_path)  # Remove metadata last.
        ASSERT.predicate(self.path, g1.files.is_empty_dir)
        return True


def init():
    repos.OpsDirs.init(_get_ops_dirs_path())


def make_ops_dirs():
    return repos.OpsDirs(
        models.REPO_XARS_DIR_NAME,
        _get_ops_dirs_path(),
        bundle_dir_type=XarBundleDir,
        ops_dir_type=XarOpsDir,
    )


def _get_ops_dirs_path():
    return bases.get_repo_path() / models.REPO_XARS_DIR_NAME
