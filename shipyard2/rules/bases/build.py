"""Set up the base environment for build processes."""

from pathlib import Path

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT

import shipyard2.rules.bases

# TODO: The build configurations of XAR images and pod images are quite
# different (e.g., XAR images use the distro Python package).  For now
# we rely on this parameter to configure the build, but we should figure
# out a more generic way to specify different build configurations.
(foreman.define_parameter.bool_typed('build-xar-image')\
 .with_doc('enable XAR image build configuration')
 .with_default(False))

(foreman.define_parameter.path_list_typed('roots')\
 .with_doc('paths to the root directory of repositories')
 .with_default([Path(__file__).parent.parent.parent.parent]))

(foreman.define_parameter.path_typed('drydock')\
 .with_doc('path to the directory of intermediate build artifacts')
 .with_default(Path.home() / 'drydock'))

# While this is not bulletproof, this should prevent accidentally
# depending on wrong build rules.
(foreman.define_parameter.bool_typed('inside-builder-pod')\
 .with_doc('do not set this parameter; this is set by build tools'))

# Install requisites for shipyard2.rules.bases.define_archive.
shipyard2.rules.bases.define_distro_packages(
    name_prefix='archive/',
    packages=[
        'tar',
        'unzip',
        'wget',
    ],
)

# Install requisites for shipyard2.rules.bases.define_git_repo.
shipyard2.rules.bases.define_distro_packages(
    name_prefix='git-repo/',
    packages=[
        'git',
    ],
)


@foreman.rule
def build(parameters):
    ASSERT.is_(parameters['inside-builder-pod'], True)
    ASSERT.all(parameters['roots'], _is_root_dir)
    with scripts.using_sudo():
        # We should run `apt-get update` even when we are not upgrading
        # the full system because some packages may be removed from the
        # distro repo while our local package index still has it.
        scripts.apt_get_update()
    scripts.mkdir(parameters['drydock'])


@foreman.rule
def cleanup(parameters):
    ASSERT.is_(parameters['inside-builder-pod'], True)
    ASSERT.all(parameters['roots'], _is_root_dir)
    with scripts.using_sudo():
        scripts.apt_get_clean()


def _is_root_dir(path):
    return (path / '.git').is_dir()


# A dummy rule for rules that want to import base parameters but don't
# want to depend on //bases:build.
foreman.define_rule('dummy')
