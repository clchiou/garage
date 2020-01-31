__all__ = [
    'init',
    'make_ops_dirs',
]

import dataclasses
import logging
import tempfile
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
from . import systemds

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

    @staticmethod
    def _get_pod_ids(metadata):
        return [config.pod_id for config in metadata.systemd_unit_configs]

    def check_invariants(self, active_ops_dirs):
        # We check uniqueness of UUIDs here, but to be honest, UUID is
        # quite unlikely to conflict.
        for ops_dir in active_ops_dirs:
            ASSERT.isdisjoint(
                set(self._get_pod_ids(ops_dir.metadata)),
                set(self._get_pod_ids(self.metadata)),
            )

    def install(self, bundle_dir, target_ops_dir_path):
        ASSERT.isinstance(bundle_dir, PodBundleDir)
        log_args = (bundle_dir.label, bundle_dir.version)
        units = {
            unit.name: unit
            for unit in bundle_dir.deploy_instruction.systemd_units
        }
        # Make metadata first so that uninstall may roll back properly.
        LOG.debug('pods install: metadata: %s %s', *log_args)
        jsons.dump_dataobject(
            self._make_metadata(bundle_dir.deploy_instruction),
            self.metadata_path,
        )
        bases.set_file_attrs(self.metadata_path)
        # Sanity check of the just-written metadata file.
        ASSERT.equal(self.label, bundle_dir.label)
        ASSERT.equal(self.version, bundle_dir.version)
        LOG.debug(
            'pods install: pod ids: %s %s: %s',
            *log_args,
            ', '.join(self._get_pod_ids(self.metadata)),
        )
        LOG.debug('pods install: volumes: %s %s', *log_args)
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
        LOG.debug('pods install: images: %s %s', *log_args)
        for _, image_path in bundle_dir.iter_images():
            ctr_scripts.ctr_import_image(image_path)
        LOG.debug('pods install: prepare pods: %s %s', *log_args)
        bases.make_dir(self.refs_dir_path)
        for config in self.metadata.systemd_unit_configs:
            pod_config = self._make_pod_config(
                bundle_dir.deploy_instruction,
                target_ops_dir_path,
                systemds.make_envs(config, self.metadata, units[config.name]),
            )
            with tempfile.NamedTemporaryFile() as config_tempfile:
                config_path = Path(config_tempfile.name)
                jsons.dump_dataobject(pod_config, config_path)
                ctr_scripts.ctr_prepare_pod(config.pod_id, config_path)
            ctr_scripts.ctr_add_ref_to_pod(
                config.pod_id, self.refs_dir_path / config.pod_id
            )
        LOG.debug('pods install: systemd units: %s %s', *log_args)
        for config in self.metadata.systemd_unit_configs:
            systemds.install(config, self.metadata, units[config.name])
        systemds.daemon_reload()
        return True

    @staticmethod
    def _make_metadata(deploy_instruction):
        return models.PodMetadata(
            label=deploy_instruction.label,
            version=deploy_instruction.version,
            images=deploy_instruction.images,
            systemd_unit_configs=[
                models.PodMetadata.SystemdUnitConfig(
                    pod_id=ctr_models.generate_pod_id(),
                    name=unit.name,
                    auto_start=unit.auto_start,
                ) for unit in deploy_instruction.systemd_units
            ],
        )

    @staticmethod
    def _make_pod_config(deploy_instruction, target_ops_dir_path, envs):

        def volume_to_mount(volume):
            return ctr_models.PodConfig.Mount(
                source=str(
                    target_ops_dir_path / \
                    models.OPS_DIR_VOLUMES_DIR_NAME /
                    volume.name
                ),
                target=volume.target,
                read_only=volume.read_only,
            )

        return dataclasses.replace(
            deploy_instruction.pod_config_template,
            apps=[
                dataclasses.replace(
                    app, exec=[arg.format_map(envs) for arg in app.exec]
                ) for app in deploy_instruction.pod_config_template.apps
            ],
            mounts=[
                *deploy_instruction.pod_config_template.mounts,
                *map(volume_to_mount, deploy_instruction.volumes),
            ],
        )

    def start(self, *, unit_names=None, all_units=False):
        ASSERT.not_all((unit_names is not None, all_units))
        LOG.info('pods start: %s %s', self.label, self.version)
        if unit_names is not None:
            predicate = lambda config: config.name in unit_names
        elif all_units:
            predicate = None
        else:
            predicate = lambda config: config.auto_start
        for config in self._filter_pod_ids_and_units(predicate):
            systemds.activate(config)

    def stop(self, *, unit_names=None):
        LOG.info('pods stop: %s %s', self.label, self.version)
        for config in self._filter_pod_ids_and_units(
            None if unit_names is None else \
            (lambda config: config.name in unit_names)
        ):
            systemds.deactivate(config)

    def _filter_pod_ids_and_units(self, predicate):
        return filter(predicate, self.metadata.systemd_unit_configs)

    def uninstall(self):
        if not self.metadata_path.exists():
            LOG.info('skip: pods uninstall: metadata was removed')
            return False
        log_args = (self.label, self.version)
        LOG.debug('pods uninstall: systemd units: %s %s', *log_args)
        for config in self.metadata.systemd_unit_configs:
            systemds.uninstall(config)
        systemds.daemon_reload()
        LOG.debug('pods uninstall: pods: %s %s', *log_args)
        g1.files.remove(self.refs_dir_path)
        for config in self.metadata.systemd_unit_configs:
            ctr_scripts.ctr_remove_pod(config.pod_id)
        LOG.debug('pods uninstall: images: %s %s', *log_args)
        for image in self.metadata.images:
            ctr_scripts.ctr_remove_image(image)
        LOG.debug('pods uninstall: volumes: %s %s', *log_args)
        g1.files.remove(self.volumes_dir_path)
        LOG.debug('pods uninstall: metadata: %s %s', *log_args)
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