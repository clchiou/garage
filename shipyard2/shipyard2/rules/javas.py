"""Helpers for writing rules for building Java applications."""

__all__ = [
    'define_root_project',
    'define_application',
]

import dataclasses
import itertools
import logging
from pathlib import Path

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT

from shipyard2 import rules

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
    @foreman.rule.depend('//bases:build')
    @foreman.rule.depend('//third-party/gradle:build')
    @foreman.rule.depend('//third-party/openjdk:build')
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
            scripts.run([
                'gradle',
                # TODO: For some unknown reason, gradle resolves the
                # relative path to /home/plumber/garage rather than
                # /usr/src/garage (maybe due to our use of overlayfs?).
                # So let us hard code the path here for now.
                '-PgarageProjectRelativePath=/usr/src/garage/java/g1',
                'wrapper',
            ])

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
    @foreman.rule.depend('//bases:build')
    @foreman.rule.depend(root_project + ':setup')
    def build(parameters):
        src_path = _find_project(parameters, foreman.get_relpath())
        root_path = _find_root_project(src_path)
        ASSERT.false(src_path.samefile(root_path))
        output_path = src_path / ('build/libs/%s-all.jar' % src_path.name)
        task = ':'.join(src_path.relative_to(root_path).parts)
        task = ':%s:shadowJar' % task
        target_dir_path = parameters[root_project + ':packages']
        if (target_dir_path / output_path.name).exists():
            LOG.info('skip: run task %s', task)
            return
        LOG.info('run task %s', task)
        with scripts.using_cwd(root_path):
            scripts.run([
                './gradlew',
                # TODO: For some unknown reason, gradle resolves the
                # relative path to /home/plumber/garage rather than
                # /usr/src/garage (maybe due to our use of overlayfs?).
                # So let us hard code the path here for now.
                '-PgarageProjectRelativePath=/usr/src/garage/java/g1',
                task,
            ])
        with scripts.using_sudo():
            scripts.mkdir(target_dir_path)
            scripts.cp(output_path, target_dir_path)

    return ApplicationRules(build=build)


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
