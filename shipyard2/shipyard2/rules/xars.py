"""Helpers for writing rules under //xars."""

__all__ = [
    'define_python_zipapp',
]

import dataclasses
import logging
from pathlib import Path

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT

import shipyard2
import shipyard2.rules
from shipyard2.rules import pythons
from shipyard2.rules import releases

LOG = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class XarRules:
    build: foreman.Rule


@dataclasses.dataclass(frozen=True)
class ZipappDeployInstruction:
    name: str
    version: str


def define_python_zipapp(
    *,
    name,
    packages,
    python_version='3',
):
    """Define a Python zipapp of first-party packages.

    This defines:
    * Parameter: name/version.
    * Rule: name/build.  NOTE: This rule is generally run in the host
      system, not inside a builder pod.
    """
    ASSERT.not_empty(packages)
    ASSERT.all(packages, lambda p: not Path(p).is_absolute())

    name_prefix = shipyard2.rules.canonicalize_name_prefix(name)
    parameter_version = name_prefix + 'version'
    rule_build = name_prefix + 'build'

    (foreman.define_parameter(parameter_version)\
     .with_doc('zipapp version'))

    @foreman.rule(rule_build)
    @foreman.rule.depend('//releases:build')
    @foreman.rule.depend('//xars/bases:build')
    def build(parameters):
        version = ASSERT.not_none(parameters[parameter_version])
        xar_dir_path = _get_xar_dir_path(parameters, name, version)
        if (
            xar_dir_path / \
            shipyard2.XAR_DIR_RELEASE_METADATA_FILENAME
        ).exists():
            LOG.info('skip: build zipapp: %s %s', name, version)
            return
        LOG.info('build zipapp: %s %s', name, version)
        try:
            scripts.mkdir(xar_dir_path)
            releases.generate_release_metadata(
                parameters,
                xar_dir_path / shipyard2.XAR_DIR_RELEASE_METADATA_FILENAME,
            )
            releases.dump(
                ZipappDeployInstruction(
                    name=name,
                    version=version,
                ),
                xar_dir_path / shipyard2.XAR_DIR_DEPLOY_INSTRUCTION_FILENAME,
            )
            _build_zipapp(
                parameters,
                'python%s' % python_version,
                packages,
                xar_dir_path / shipyard2.XAR_DIR_ZIPAPP_FILENAME,
            )
        except Exception:
            # Roll back on error.
            scripts.rm(xar_dir_path, recursive=True)
            raise

    return XarRules(build=build)


def _get_xar_dir_path(parameters, name, version):
    return (
        parameters['//releases:root'] / \
        foreman.get_relpath() /
        name /
        version
    )


def _build_zipapp(parameters, python_exec, packages, zipapp_path):
    ASSERT.predicate(zipapp_path, Path.is_absolute)
    scripts.export_path(
        'PYTHONPATH',
        pythons.find_package(parameters, 'py/g1/devtools/buildtools'),
    )
    # TODO: Remove this once startup is migrated to
    # g1.devtools.buildtools.
    scripts.export_path(
        'PYTHONPATH',
        pythons.find_package(parameters, 'py/buildtools'),
    )
    for package in packages:
        with scripts.using_cwd(pythons.find_package(parameters, package)):
            # Clean up any previous build, just in case.
            scripts.rm('build', recursive=True)
            scripts.run([
                python_exec,
                'setup.py',
                'build',
                'bdist_zipapp',
                *('--output', zipapp_path),
            ])
