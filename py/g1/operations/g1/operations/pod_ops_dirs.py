__all__ = [
    'PodBundleDir',
    'make_pod_ops_dirs',
]

import dataclasses
import logging
from pathlib import Path

import g1.files
from g1 import scripts
from g1.bases.assertions import ASSERT
from g1.containers import models as ctr_models
from g1.containers import scripts as ctr_scripts
from g1.texts import jsons

from . import bases
from . import models
from . import repos

LOG = logging.getLogger(__name__)


class PodBundleDir(repos.BundleDirInterface):

    deploy_instruction_type = models.PodDeployInstruction

    def __init__(self, path):
        self.path_unchecked = path

    def _get_image_path(self, image):
        return (
            self.path_unchecked / \
            models.POD_BUNDLE_IMAGES_DIR_NAME /
            image.name /
            models.POD_BUNDLE_IMAGE_FILENAME
        )

    def get_volume_path(self, volume):
        return (
            self.path_unchecked / \
            models.POD_BUNDLE_VOLUMES_DIR_NAME /
            volume.name /
            models.POD_BUNDLE_VOLUME_FILENAME
        )

    def check(self):
        ASSERT.predicate(self.path_unchecked, Path.is_dir)
        deploy_instruction = self.load_deploy_instruction()
        for image in deploy_instruction.images:
            ASSERT.predicate(self._get_image_path(image), Path.is_file)
        for volume in deploy_instruction.volumes:
            ASSERT.predicate(self.get_volume_path(volume), Path.is_file)

    def install(self):
        LOG.info('pods install images: %s %s', self.label, self.version)
        for image in self.deploy_instruction.images:
            ctr_scripts.ctr_import_image(self._get_image_path(image))
        return True

    def uninstall(self):
        return _uninstall(self, self.deploy_instruction.images)


def _uninstall(dir_obj, images):
    LOG.info('pods uninstall images: %s %s', dir_obj.label, dir_obj.version)
    for image in images:
        ctr_scripts.ctr_remove_image(image)
    return True


class PodOpsDir(repos.OpsDirInterface):

    metadata_type = models.PodMetadata

    def __init__(self, path):
        self.path_unchecked = path

    def init(self):
        bases.make_dir(self.path_unchecked)

    def check(self):
        ASSERT.predicate(self.path_unchecked, Path.is_dir)

    def cleanup(self):
        g1.files.remove(self.volumes_dir_path)
        g1.files.remove(self.metadata_path)
        ASSERT.predicate(self.path, g1.files.is_empty_dir)

    def check_invariants(self, active_ops_dirs):
        self.check()
        ASSERT.predicate(self.metadata_path, Path.is_file)
        # We check uniqueness of UUIDs here, but to be honest, UUID is
        # quite unlikely to conflict.
        for ops_dir in active_ops_dirs:
            ASSERT(
                ops_dir.metadata.pod_id != self.metadata.pod_id,
                'expect unique pod id: {}',
                self.metadata.pod_id,
            )

    def init_from_bundle_dir(self, bundle_dir, target_ops_dir_path):
        # Generate pod metadata.
        pod_id = ctr_models.generate_pod_id()
        LOG.info('generate pod metadata: %s', pod_id)
        jsons.dump_dataobject(
            models.PodMetadata(
                label=bundle_dir.label,
                pod_id=pod_id,
                pod_config=dataclasses.replace(
                    bundle_dir.deploy_instruction.pod_config_template,
                    mounts=self._generate_mounts(
                        bundle_dir.deploy_instruction,
                        target_ops_dir_path,
                    ),
                ),
            ),
            self.metadata_path,
        )
        bases.set_file_attrs(self.metadata_path)
        # Extract volumes.
        bases.make_dir(self.volumes_dir_path)
        for volume in bundle_dir.deploy_instruction.volumes:
            tarball_path = bundle_dir.get_volume_path(volume)
            volume_dir_path = self.volumes_dir_path / volume.name
            LOG.info('extract volume: %s -> %s', tarball_path, volume_dir_path)
            bases.make_dir(volume_dir_path)
            scripts.tar_extract(
                tarball_path,
                directory=volume_dir_path,
                extra_args=(
                    '--same-owner',
                    '--same-permissions',
                ),
            )

    @staticmethod
    def _generate_mounts(deploy_instruction, target_ops_dir_path):
        mounts = list(deploy_instruction.pod_config_template.mounts)
        for volume in deploy_instruction.volumes:
            mounts.append(
                ctr_models.PodConfig.Mount(
                    source=str(
                        target_ops_dir_path / \
                        models.OPS_DIR_VOLUMES_DIR_NAME /
                        volume.name
                    ),
                    target=volume.target,
                    read_only=volume.read_only,
                )
            )
        return mounts

    def activate(self):
        pass  # Nothing here.

    def deactivate(self):
        pass  # Nothing here.

    def uninstall(self):
        return _uninstall(self, self.metadata.images)


def make_pod_ops_dirs():
    return repos.OpsDirs(
        models.REPO_PODS_DIR_NAME,
        bases.get_repo_path() / models.REPO_PODS_DIR_NAME,
        bundle_dir_type=PodBundleDir,
        ops_dir_type=PodOpsDir,
    )
