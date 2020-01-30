__all__ = [
    'init',
    'make_ops_dirs',
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


class PodBundleDir(repos.AbstractBundleDir):

    deploy_instruction_type = models.PodDeployInstruction

    def post_init(self):
        ASSERT.predicate(self.path, Path.is_dir)
        ASSERT.predicate(self.deploy_instruction_path, Path.is_file)
        ASSERT.all((path for _, path in self.iter_images()), Path.is_file)
        ASSERT.all((path for _, path in self.iter_volumes()), Path.is_file)

    def iter_images(self):
        for image in self.deploy_instruction.images:
            yield image, (
                self.path / \
                models.POD_BUNDLE_IMAGES_DIR_NAME /
                image.name /
                models.POD_BUNDLE_IMAGE_FILENAME
            )

    def iter_volumes(self):
        for volume in self.deploy_instruction.volumes:
            yield volume, (
                self.path / \
                models.POD_BUNDLE_VOLUMES_DIR_NAME /
                volume.name /
                models.POD_BUNDLE_VOLUME_FILENAME
            )


class PodOpsDir(repos.AbstractOpsDir):

    metadata_type = models.PodMetadata

    def check_invariants(self, active_ops_dirs):
        # We check uniqueness of UUIDs here, but to be honest, UUID is
        # quite unlikely to conflict.
        for ops_dir in active_ops_dirs:
            ASSERT(
                ops_dir.metadata.pod_id != self.metadata.pod_id,
                'expect unique pod id: {}',
                self.metadata.pod_id,
            )

    def install(self, bundle_dir, target_ops_dir_path):
        ASSERT.isinstance(bundle_dir, PodBundleDir)
        log_args = (bundle_dir.label, bundle_dir.version)

        pod_id = ctr_models.generate_pod_id()
        LOG.info('pods install: metadata: %s %s %s', *log_args, pod_id)
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
        # Sanity check of the just-written metadata file.
        ASSERT.equal(self.label, bundle_dir.label)
        ASSERT.equal(self.version, bundle_dir.version)

        LOG.info('pods install: images: %s %s', *log_args)
        for _, image_path in bundle_dir.iter_images():
            ctr_scripts.ctr_import_image(image_path)

        LOG.info('pods install: volumes: %s %s', *log_args)
        bases.make_dir(self.volumes_dir_path)
        for volume, volume_path in bundle_dir.iter_volumes():
            volume_dir_path = self.volumes_dir_path / volume.name
            LOG.debug('pods: extract: %s -> %s', volume_path, volume_dir_path)
            bases.make_dir(ASSERT.not_predicate(volume_dir_path, Path.exists))
            scripts.tar_extract(
                volume_path,
                directory=volume_dir_path,
                extra_args=(
                    '--same-owner',
                    '--same-permissions',
                ),
            )

        return True

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

    def start(self):
        pass  # Nothing here.

    def stop(self):
        pass  # Nothing here.

    def uninstall(self):
        if not self.metadata_path.exists():
            LOG.info('skip: pods uninstall: metadata was removed')
            return False
        LOG.info('pods uninstall: images: %s %s', self.label, self.version)
        for image in self.metadata.images:
            ctr_scripts.ctr_remove_image(image)
        g1.files.remove(self.volumes_dir_path)
        g1.files.remove(self.metadata_path)  # Remove metadata last.
        ASSERT.predicate(self.path, g1.files.is_empty_dir)
        return True


def init():
    repos.OpsDirs.init(_get_ops_dirs_path())


def make_ops_dirs():
    return repos.OpsDirs(
        models.REPO_PODS_DIR_NAME,
        _get_ops_dirs_path(),
        bundle_dir_type=PodBundleDir,
        ops_dir_type=PodOpsDir,
    )


def _get_ops_dirs_path():
    return bases.get_repo_path() / models.REPO_PODS_DIR_NAME
