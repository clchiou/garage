"""Helpers for writing rules under //xars."""

__all__ = [
    'define_xar',
    'define_zipapp',
]

import dataclasses
import logging
from pathlib import Path

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT
from g1.containers import models as ctr_models
from g1.operations.cores import models as ops_models

import shipyard2
import shipyard2.rules
from shipyard2.rules import images
from shipyard2.rules import pythons
from shipyard2.rules import releases

LOG = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class XarRules:
    build: foreman.Rule


@dataclasses.dataclass(frozen=True)
class ZipappRules:
    build: foreman.Rule


def _run_build(build_func, parameters, kind, name, version, **kwargs):
    xar_dir_path = releases.get_output_dir_path(parameters, name, version)
    metadata_path = xar_dir_path / shipyard2.XAR_DIR_RELEASE_METADATA_FILENAME
    if metadata_path.exists():
        LOG.info('skip: build %s: %s %s', kind, name, version)
        return
    LOG.info('build %s: %s %s', kind, name, version)
    try:
        scripts.mkdir(xar_dir_path)
        releases.generate_release_metadata(parameters, metadata_path)
        build_func(parameters, name, version, xar_dir_path, **kwargs)
    except Exception:
        # Roll back on error.
        scripts.rm(xar_dir_path, recursive=True)
        raise


def define_xar(
    *,
    name,
    exec_relpath,
    image,
):
    """Define a XAR.

    This defines:
    * Parameter: name/version.
    * Rule: name/build.  NOTE: This rule is generally run in the host
      system, not inside a builder pod.
    """
    ASSERT.not_predicate(Path(exec_relpath), Path.is_absolute)
    # Let's require absolute image label for now as it is quite hard to
    # derive label path from xar's relpath.
    ASSERT.startswith(image, '//')

    name_prefix = shipyard2.rules.canonicalize_name_prefix(name)
    parameter_version = name_prefix + 'version'
    rule_build = name_prefix + 'build'

    (foreman.define_parameter(parameter_version)\
     .with_doc('xar version'))

    image = foreman.Label.parse(image)

    @foreman.rule(rule_build)
    @foreman.rule.depend('//releases:build')
    @foreman.rule.depend('//xars/bases:build')
    @foreman.rule.depend(str(images.derive_rule(image)))
    def build(parameters):
        _run_build(
            _build_xar,
            parameters,
            'xar',
            name,
            ASSERT.not_none(parameters[parameter_version]),
            exec_relpath=exec_relpath,
            image=image,
        )

    return XarRules(build=build)


def _build_xar(
    parameters, name, version, xar_dir_path, *, exec_relpath, image
):
    releases.dump(
        ops_models.XarDeployInstruction(
            label=str(releases.get_output_label(name)),
            version=version,
            exec_relpath=exec_relpath,
            image=ctr_models.PodConfig.Image(
                name=str(image.name),
                version=images.get_image_version(parameters, image),
            ),
        ),
        xar_dir_path / shipyard2.XAR_DIR_DEPLOY_INSTRUCTION_FILENAME,
    )
    scripts.make_relative_symlink(
        images.derive_image_path(parameters, image),
        xar_dir_path / shipyard2.XAR_DIR_IMAGE_FILENAME,
    )


def define_zipapp(
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
        _run_build(
            _build_zipapp,
            parameters,
            'zipapp',
            name,
            ASSERT.not_none(parameters[parameter_version]),
            python_exec='python%s' % python_version,
            packages=packages,
        )

    return ZipappRules(build=build)


def _build_zipapp(
    parameters, name, version, xar_dir_path, *, python_exec, packages
):
    releases.dump(
        ops_models.XarDeployInstruction(
            label=str(releases.get_output_label(name)),
            version=version,
            exec_relpath=None,
            image=None,
        ),
        xar_dir_path / shipyard2.XAR_DIR_DEPLOY_INSTRUCTION_FILENAME,
    )
    _package_zipapp(
        parameters,
        python_exec,
        packages,
        xar_dir_path / shipyard2.XAR_DIR_ZIPAPP_FILENAME,
    )


def _package_zipapp(parameters, python_exec, packages, zipapp_path):
    # zipapp packaging might not work correctly on existing zipapp.
    ASSERT.not_predicate(zipapp_path, Path.exists)
    # We will change working directory when running setup.py so let's
    # make sure that zipapp output path is absolute.
    ASSERT.predicate(zipapp_path, Path.is_absolute)
    scripts.export_path(
        'PYTHONPATH',
        pythons.find_package(parameters, 'python/g1/devtools/buildtools'),
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
