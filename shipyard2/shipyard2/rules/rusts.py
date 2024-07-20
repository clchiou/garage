__all__ = [
    'define_binary',
]

import dataclasses
import logging
from pathlib import Path

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT

import shipyard2
from shipyard2.rules import releases

LOG = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class BinaryRules:
    build: foreman.Rule


def define_binary(package_relpath):
    """Define a binary package.

    This defines:
    * Parameter: name/version.
    * Rule: name/build.  NOTE: This rule is generally run in the
      host system, not inside a builder pod.
    """
    name = Path(package_relpath).name
    parameter_version = name + '/version'
    rule_build = name + '/build'

    (foreman.define_parameter(parameter_version)\
     .with_doc('binary version'))

    # NOTE: This does not depend on //bases:build because it is run
    # outside a builder pod.
    @foreman.rule(rule_build)
    @foreman.rule.depend('//releases:build')
    def build(parameters):
        package_path = _find_package(parameters, package_relpath)
        workspace_path = _find_workspace(package_path)

        version = ASSERT.not_none(parameters[parameter_version])

        bin_dir_path = releases.get_output_dir_path(parameters, name, version)
        metadata_path = (
            bin_dir_path / shipyard2.BIN_DIR_RELEASE_METADATA_FILENAME
        )

        if metadata_path.exists():
            LOG.info('skip: build rust binary: %s %s', name, version)
            return
        LOG.info('build rust binary: %s %s', name, version)

        with scripts.using_cwd(package_path):
            # APP_VERSION is read by g1_cli::version.
            with scripts.merging_env({'APP_VERSION': version}):
                scripts.run(['cargo', 'build', '--release'])

        try:
            scripts.mkdir(bin_dir_path)
            releases.generate_release_metadata(parameters, metadata_path)
            scripts.cp(
                workspace_path / 'target' / 'release' / name,
                bin_dir_path / name,
            )
        except Exception:
            # Roll back on error.
            scripts.rm(bin_dir_path, recursive=True)
            raise

    return BinaryRules(build=build)


def _find_package(parameters, relpath):
    root_paths = parameters['//bases:roots']
    for root_path in root_paths:
        path = root_path / relpath
        if _is_package(path):
            return path
    return ASSERT.unreachable(
        'cannot find package {} under: {}', relpath, root_paths
    )


def _find_workspace(package_path):
    for path in package_path.parents:
        if _is_package(path):
            return path
    return ASSERT.unreachable('cannot find workspace from: {}', package_path)


def _is_package(path):
    return (path / 'Cargo.toml').exists()
