"""Helpers for writing rules that depends on //bases."""

__all__ = [
    'define_archive',
    'define_distro_packages',
    'define_git_repo',
]

import collections
import dataclasses
import logging
from pathlib import Path

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT

from shipyard2 import rules

LOG = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class ArchiveRules:
    download: foreman.Rule
    extract: foreman.Rule


Archive = collections.namedtuple(
    'Archive',
    [
        'url',
        'filename',  # Archive file name (foo.tgz).
        'output',  # Extracted output directory name (foo).
        'checksum',
    ],
)


def define_archive(
    url,
    *,
    name_prefix='',
    filename=None,
    output=None,
    checksum=None,
    wget_headers=(),
):
    """Define an archive.

    This defines:
    * Parameter: [name_prefix/]archive.
    * Rule: [name_prefix/]download.
    * Rule: [name_prefix/]extract.
    """
    name_prefix = rules.canonicalize_name_prefix(name_prefix)
    parameter_archive = name_prefix + 'archive'
    rule_download = name_prefix + 'download'
    rule_extract = name_prefix + 'extract'

    (foreman.define_parameter.namedtuple_typed(Archive, parameter_archive)\
     .with_doc('archive info')
     .with_default(_archive_make(url, filename, output, checksum)))

    @foreman.rule(rule_download)
    @foreman.rule.depend('//bases:archive/install')
    @foreman.rule.depend('//bases:build')
    def download(parameters):
        archive = parameters[parameter_archive]
        archive_path = _archive_get_archive_path(parameters, archive)
        if archive_path.exists():
            LOG.info('skip: download archive: %s', archive.url)
            return
        LOG.info('download archive: %s', archive.url)
        scripts.mkdir(archive_path.parent)
        scripts.wget(
            archive.url,
            output_path=archive_path,
            headers=wget_headers,
        )
        ASSERT.predicate(archive_path, Path.is_file)
        if archive.checksum:
            scripts.validate_checksum(archive_path, archive.checksum)

    @foreman.rule(rule_extract)
    @foreman.rule.depend('//bases:archive/install')
    @foreman.rule.depend('//bases:build')
    @foreman.rule.depend(rule_download)
    def extract(parameters):
        archive = parameters[parameter_archive]
        archive_path = _archive_get_archive_path(parameters, archive)
        output_path = _archive_get_output_path(parameters, archive)
        if output_path.exists():
            LOG.info('skip: extract archive: %s', archive_path)
            return
        LOG.info('extract archive: %s', archive_path)
        scripts.mkdir(output_path.parent)
        scripts.extract(archive_path, directory=output_path.parent)
        ASSERT.predicate(output_path, Path.is_dir)

    return ArchiveRules(download=download, extract=extract)


def _archive_make(url, filename, output, checksum):
    if filename is None:
        filename = scripts.get_url_path(url).name
    if output is None:
        output = scripts.remove_archive_suffix(filename)
    return Archive(
        url=url,
        filename=filename,
        output=output,
        checksum=checksum,
    )


def _archive_get_archive_path(parameters, archive):
    return (
        parameters['//bases:drydock'] / foreman.get_relpath() /
        archive.filename
    )


def _archive_get_output_path(parameters, archive):
    return (
        parameters['//bases:drydock'] / foreman.get_relpath() / archive.output
    )


@dataclasses.dataclass(frozen=True)
class DistroPackagesRules:
    install: foreman.Rule


def define_distro_packages(
    packages,
    *,
    name_prefix='',
):
    """Define distro packages.

    This defines:
    * Parameter: [name_prefix/]packages.
    * Rule: [name_prefix/]install.
    """
    name_prefix = rules.canonicalize_name_prefix(name_prefix)
    parameter_packages = name_prefix + 'packages'
    rule_install = name_prefix + 'install'

    (foreman.define_parameter.list_typed(parameter_packages)\
     .with_default(packages))

    @foreman.rule(rule_install)
    @foreman.rule.depend('//bases:build')
    def install(parameters):
        with scripts.using_sudo():
            scripts.apt_get_install(parameters[parameter_packages])

    return DistroPackagesRules(install=install)


@dataclasses.dataclass(frozen=True)
class GitRepoRules:
    git_clone: foreman.Rule


def define_git_repo(
    repo_url,
    treeish,
    *,
    name_prefix='',
):
    """Define a git repo.

    Given a rule "//rule/path/foo", this checks out the repo and its
    sub modules into "drydock/rule/path/foo/foo".  Note the extra "foo"
    of the repo path - since the repo is checked into a sub directory,
    you may use the parent directory as a scratch pad.

    This defines:
    * Rule: [name_prefix/]git-clone.
    """
    name_prefix = rules.canonicalize_name_prefix(name_prefix)
    rule_git_clone = name_prefix + 'git-clone'

    @foreman.rule(rule_git_clone)
    @foreman.rule.depend('//bases:build')
    @foreman.rule.depend('//bases:git-repo/install')
    def git_clone(parameters):
        repo_path = parameters['//bases:drydock'] / foreman.get_relpath()
        repo_path /= repo_path.name
        git_dir_path = repo_path / '.git'
        if git_dir_path.is_dir():
            LOG.info('skip: git clone: %s', repo_url)
            return
        LOG.info('git clone: %s', repo_url)
        scripts.git_clone(repo_url, repo_path=repo_path, treeish=treeish)
        ASSERT.predicate(git_dir_path, Path.is_dir)

    return GitRepoRules(git_clone=git_clone)
