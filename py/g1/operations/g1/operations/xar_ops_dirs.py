__all__ = [
    'XarBundleDir',
    'make_xar_ops_dirs',
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


class XarBundleDir(repos.BundleDirInterface):

    deploy_instruction_type = models.XarDeployInstruction

    def __init__(self, path):
        self.path_unchecked = path

    def check(self):
        ASSERT.predicate(self.path_unchecked, Path.is_dir)
        if self.load_deploy_instruction().is_zipapp():
            ASSERT.predicate(
                self.path_unchecked / models.XAR_BUNDLE_ZIPAPP_FILENAME,
                Path.is_file,
            )
        else:
            ASSERT.predicate(
                self.path_unchecked / models.XAR_BUNDLE_IMAGE_FILENAME,
                Path.is_file,
            )

    @property
    def zipapp_path(self):
        ASSERT.true(self.deploy_instruction.is_zipapp())
        return self.path / models.XAR_BUNDLE_ZIPAPP_FILENAME

    @property
    def image_path(self):
        ASSERT.false(self.deploy_instruction.is_zipapp())
        return self.path / models.XAR_BUNDLE_IMAGE_FILENAME

    def install(self):
        if self.deploy_instruction.is_zipapp():
            LOG.info('xars install zipapp: %s %s', self.label, self.version)
            bases.copy_exec(
                self.zipapp_path,
                bases.get_zipapp_target_path(self.deploy_instruction.name),
            )
        else:
            LOG.info('xars install xar: %s %s', self.label, self.version)
            ctr_scripts.ctr_import_image(self.image_path)
            ctr_scripts.ctr_install_xar(
                self.deploy_instruction.name,
                self.deploy_instruction.exec_relpath,
                self.deploy_instruction.image,
            )
        return True

    def uninstall(self):
        return _uninstall(self, self.deploy_instruction)


def _uninstall(dir_obj, inst_like_obj):
    log_args = (dir_obj.label, dir_obj.version)
    if inst_like_obj.is_zipapp():
        LOG.info('xars uninstall zipapp: %s %s', *log_args)
        g1.files.remove(bases.get_zipapp_target_path(inst_like_obj.name))
    else:
        LOG.info('xars uninstall xar: %s %s', *log_args)
        ctr_scripts.ctr_uninstall_xar(inst_like_obj.name)
        ctr_scripts.ctr_remove_image(inst_like_obj.image)
    return True


class XarOpsDir(repos.OpsDirInterface):

    metadata_type = models.XarMetadata

    def __init__(self, path):
        self.path_unchecked = path

    def init(self):
        bases.make_dir(self.path_unchecked)

    def check(self):
        ASSERT.predicate(self.path_unchecked, Path.is_dir)

    @property
    def zipapp_target_path(self):
        ASSERT.true(self.metadata.is_zipapp())
        return bases.get_zipapp_target_path(self.metadata.name)

    def cleanup(self):
        g1.files.remove(self.metadata_path)
        ASSERT.predicate(self.path, g1.files.is_empty_dir)

    def check_invariants(self, active_ops_dirs):
        self.check()
        ASSERT.predicate(self.metadata_path, Path.is_file)
        for ops_dir in active_ops_dirs:
            ASSERT(
                ops_dir.metadata.name != self.metadata.name,
                'expect unique xar label name: {}, {}',
                ops_dir.label,
                self.label,
            )

    def init_from_bundle_dir(self, bundle_dir, target_ops_dir_path):
        del target_ops_dir_path  # Unused.
        jsons.dump_dataobject(
            models.XarMetadata(
                label=bundle_dir.label,
                version=bundle_dir.version,
                image=bundle_dir.deploy_instruction.image,
            ),
            self.metadata_path,
        )
        bases.set_file_attrs(self.metadata_path)

    def activate(self):
        pass  # Nothing here.

    def deactivate(self):
        pass  # Nothing here.

    def uninstall(self):
        return _uninstall(self, self.metadata)


def make_xar_ops_dirs():
    return repos.OpsDirs(
        models.REPO_XARS_DIR_NAME,
        bases.get_repo_path() / models.REPO_XARS_DIR_NAME,
        bundle_dir_type=XarBundleDir,
        ops_dir_type=XarOpsDir,
    )
