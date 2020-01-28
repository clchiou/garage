__all__ = [
    'XarBundleDir',
    'make_xar_ops_dirs',
]

import logging
from pathlib import Path

import g1.files
from g1.bases import classes
from g1.bases.assertions import ASSERT
from g1.containers import scripts as ctr_scripts
from g1.texts import jsons

from . import bases
from . import models
from . import repos

LOG = logging.getLogger(__name__)


class XarBundleDir(repos.BundleDirInterface):

    def __init__(self, path):
        self.path_unchecked = path

    def _check(self):
        ASSERT.predicate(self.path_unchecked, Path.is_dir)
        deploy_instruction = jsons.load_dataobject(
            models.XarDeployInstruction,
            ASSERT.predicate(
                self.path_unchecked / \
                models.BUNDLE_DEPLOY_INSTRUCTION_FILENAME,
                Path.is_file,
            )
        )
        if deploy_instruction.is_zipapp():
            ASSERT.predicate(
                self.path_unchecked / models.XAR_BUNDLE_ZIPAPP_FILENAME,
                Path.is_file,
            )
        else:
            ASSERT.predicate(
                self.path_unchecked / models.XAR_BUNDLE_IMAGE_FILENAME,
                Path.is_file,
            )
        return deploy_instruction

    def check(self):
        self._check()

    # XXX: This annotation works around pylint no-member false errors.
    deploy_instruction: models.XarDeployInstruction

    @classes.memorizing_property
    def deploy_instruction(self):  # pylint: disable=function-redefined
        return self._check()

    @property
    def name(self):
        return self.deploy_instruction.name

    @property
    def version(self):
        return self.deploy_instruction.version

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
            LOG.info('xars install zipapp: %s %s', self.name, self.version)
            bases.copy_exec(
                self.zipapp_path,
                bases.get_zipapp_target_path(self.deploy_instruction.name),
            )
        else:
            LOG.info('xars install xar: %s %s', self.name, self.version)
            ctr_scripts.ctr_import_image(self.image_path)
            ctr_scripts.ctr_install_xar(
                self.deploy_instruction.name,
                self.deploy_instruction.exec_relpath,
                self.deploy_instruction.image,
            )
        return True

    def uninstall(self):
        if self.deploy_instruction.is_zipapp():
            LOG.info('xars uninstall zipapp: %s %s', self.name, self.version)
            path = bases.get_zipapp_target_path(self.deploy_instruction.name)
            if path.exists():
                path.unlink()
        else:
            LOG.info('xars uninstall xar: %s %s', self.name, self.version)
            ctr_scripts.ctr_uninstall_xar(self.deploy_instruction.name)
            ctr_scripts.ctr_remove_image(self.deploy_instruction.image)
        return True


class XarOpsDir(repos.OpsDirInterface):

    @staticmethod
    def _load_metadata(xar_ops_dir_path):
        return jsons.load_dataobject(
            models.XarMetadata,
            xar_ops_dir_path / models.OPS_DIR_METADATA_FILENAME,
        )

    def __init__(self, path):
        self.path_unchecked = path

    def init(self):
        bases.make_dir(self.path_unchecked)

    def check(self):
        ASSERT.predicate(self.path_unchecked, Path.is_dir)

    # XXX: This annotation works around pylint no-member false errors.
    _metadata_path: Path

    @classes.memorizing_property
    def _metadata_path(self):  # pylint: disable=function-redefined
        return self.path / models.OPS_DIR_METADATA_FILENAME

    # XXX: This annotation works around pylint no-member false errors.
    metadata: models.XarMetadata

    @classes.memorizing_property
    def metadata(self):  # pylint: disable=function-redefined
        return self._load_metadata(self.path)

    @property
    def zipapp_target_path(self):
        ASSERT.true(self.metadata.is_zipapp())
        return bases.get_zipapp_target_path(self.metadata.name)

    def cleanup(self):
        if self._metadata_path.exists():
            self._metadata_path.unlink()
        ASSERT.predicate(self.path, g1.files.is_empty_dir)

    def check_invariants(self, active_ops_dirs):
        self.check()
        ASSERT.predicate(self._metadata_path, Path.is_file)
        for ops_dir in active_ops_dirs:
            metadata = self._load_metadata(ops_dir.path)
            ASSERT(
                metadata.name != self.metadata.name,
                'expect unique xar name: {}',
                self.metadata.name,
            )

    @staticmethod
    def get_ops_dir_name(name, version):
        # Underscore '_' is not a validate character of name and version
        # for now; so it is safe to join name and version with it.
        return '%s_%s' % (name, version)

    def init_from_bundle_dir(self, bundle_dir):
        deploy_instruction = bundle_dir.deploy_instruction
        jsons.dump_dataobject(
            models.XarMetadata(
                name=deploy_instruction.name,
                version=deploy_instruction.version,
                image=deploy_instruction.image,
            ),
            self._metadata_path,
        )
        bases.set_file_attrs(self._metadata_path)

    def activate(self):
        pass  # Nothing here.

    def deactivate(self):
        pass  # Nothing here.

    def uninstall(self):
        name = self.metadata.name
        version = self.metadata.version
        if self.metadata.is_zipapp():
            LOG.info('xars uninstall zipapp: %s %s', name, version)
            path = bases.get_zipapp_target_path(name)
            if path.exists():
                path.unlink()
        else:
            LOG.info('xars uninstall xar: %s %s', name, version)
            ctr_scripts.ctr_uninstall_xar(name)
            ctr_scripts.ctr_remove_image(self.metadata.image)
        return True


def make_xar_ops_dirs():
    return repos.OpsDirs(
        models.REPO_XARS_DIR_NAME,
        bases.get_repo_path() / models.REPO_XARS_DIR_NAME,
        bundle_dir_type=XarBundleDir,
        ops_dir_type=XarOpsDir,
    )
