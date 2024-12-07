"""Helpers for writing rules for building Java applications."""

__all__ = [
    'define_root_project',
    'define_application',
    'define_binary',
]

import dataclasses
import itertools
import logging
from pathlib import Path

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT

import shipyard2
from shipyard2 import rules
from shipyard2.rules import releases

LOG = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class RootProjectRules:
    setup: foreman.Rule


def define_root_project():
    """Define the root project.

    This defines:
    * Parameter: packages.
    * Rule: setup.
    """

    (foreman.define_parameter.path_typed('packages')\
     .with_doc('path to directory of Java packages')
     .with_default(Path('/usr/local/lib/java/packages')))

    @foreman.rule
    @foreman.rule.depend(
        '//bases:build',
        when=lambda ps: ps['//bases:inside-builder-pod'] is True,
    )
    @foreman.rule.depend(
        '//third-party/gradle:build',
        when=lambda ps: ps['//bases:inside-builder-pod'] is True,
    )
    @foreman.rule.depend(
        '//third-party/openjdk:build',
        when=lambda ps: ps['//bases:inside-builder-pod'] is True,
    )
    @foreman.rule.depend(
        '//releases:build',
        when=lambda ps: ps['//bases:inside-builder-pod'] is False,
    )
    def setup(parameters):
        src_path = ASSERT.predicate(
            _find_project(parameters, foreman.get_relpath()),
            _is_root_project,
        )
        if (src_path / 'gradlew').exists():
            LOG.info('skip: generate gradle wrapper')
            return
        LOG.info('generate gradle wrapper')
        with scripts.using_cwd(src_path):
            scripts.run(['gradle', 'wrapper'])

    return RootProjectRules(setup=setup)


@dataclasses.dataclass(frozen=True)
class ApplicationRules:
    build: foreman.Rule


def define_application(root_project, *, name_prefix=''):
    """Define a first-party fat-JAR application.

    This defines:
    * Rule: [name_prefix]/build.
    """
    name_prefix = rules.canonicalize_name_prefix(name_prefix)
    rule_build = name_prefix + 'build'

    @foreman.rule(rule_build)
    @foreman.rule.depend(
        '//bases:build',
        when=lambda ps: ps['//bases:inside-builder-pod'] is True,
    )
    @foreman.rule.depend(
        '//releases:build',
        when=lambda ps: ps['//bases:inside-builder-pod'] is False,
    )
    @foreman.rule.depend(root_project + ':setup')
    def build(parameters):
        inside_builder_pod = parameters['//bases:inside-builder-pod'] is True

        src_path = _find_project(parameters, foreman.get_relpath())
        root_path = _find_root_project(src_path)
        ASSERT.false(src_path.samefile(root_path))
        jar_path = _get_jar_path(src_path)
        target_dir_path = parameters[root_project + ':packages']

        task = ':'.join(src_path.relative_to(root_path).parts)
        task = ':%s:shadowJar' % task

        if inside_builder_pod and (target_dir_path / jar_path.name).exists():
            LOG.info('skip: run task %s', task)
            return

        LOG.info('run task %s', task)
        with scripts.using_cwd(root_path):
            scripts.run(['./gradlew', task])

        if inside_builder_pod:
            with scripts.using_sudo():
                scripts.mkdir(target_dir_path)
                scripts.cp(jar_path, target_dir_path)

    return ApplicationRules(build=build)


@dataclasses.dataclass(frozen=True)
class BinaryRules:
    build: foreman.Rule


def define_binary(name, application):
    """Define a binary package.

    This defines:
    * Parameter: name/version.
    * Rule: name/build.  NOTE: This rule is generally run in the
      host system, not inside a builder pod.
    """

    parameter_version = name + '/version'
    rule_build = name + '/build'

    (foreman.define_parameter(parameter_version)\
     .with_doc('binary version'))

    # NOTE: This does not depend on //bases:build because it is run
    # outside a builder pod.
    @foreman.rule(rule_build)
    @foreman.rule.depend('//releases:build')
    @foreman.rule.depend(application + ':build')
    def build(parameters):
        src_path = _find_project(
            parameters,
            ASSERT.startswith(application, '//')[2:],
        )
        jar_path = _get_jar_path(src_path)

        version = ASSERT.not_none(parameters[parameter_version])

        bin_dir_path = releases.get_output_dir_path(parameters, name, version)
        metadata_path = (
            bin_dir_path / shipyard2.BIN_DIR_RELEASE_METADATA_FILENAME
        )

        if metadata_path.exists():
            LOG.info('skip: copy jar: %s %s', name, version)
            return
        LOG.info('copy jar: %s %s', name, version)

        try:
            scripts.mkdir(bin_dir_path)
            releases.generate_release_metadata(parameters, metadata_path)
            scripts.cp(jar_path, bin_dir_path / jar_path.name)
            with scripts.using_cwd(bin_dir_path):
                # Comply with the basic structure of the bin directory.
                scripts.ln(jar_path.name, name)
        except Exception:
            # Roll back on error.
            scripts.rm(bin_dir_path, recursive=True)
            raise

    return BinaryRules(build=build)


def _find_project(parameters, relpath):
    root_paths = parameters['//bases:roots']
    for root_path in root_paths:
        path = root_path / relpath
        if (path / 'build.gradle').exists():
            return path
    return ASSERT.unreachable(
        'cannot find project {} under: {}', relpath, root_paths
    )


def _find_root_project(src_path):
    for path in itertools.chain([src_path], src_path.parents):
        if _is_root_project(path):
            return path
    return ASSERT.unreachable('cannot find root project from: {}', src_path)


def _is_root_project(path):
    return (path / 'settings.gradle').exists()


def _get_jar_path(src_path):
    return src_path / ('build/libs/%s-all.jar' % src_path.name)
