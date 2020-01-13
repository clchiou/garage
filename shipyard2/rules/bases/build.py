"""Set up the base environment for build processes."""

from pathlib import Path

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT

import shipyard2.rules.bases

(foreman.define_parameter.path_list_typed('roots')\
 .with_doc('paths to the root directory of repositories')
 .with_default([Path(__file__).parent.parent.parent.parent]))

(foreman.define_parameter.path_typed('drydock')\
 .with_doc('path to the directory of intermediate build artifacts')
 .with_default(Path.home() / 'drydock'))

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
    ASSERT.all(parameters['roots'], _is_root_dir)
    scripts.mkdir(parameters['drydock'])


def _is_root_dir(path):
    return (path / '.git').is_dir()


# A dummy rule for rules that want to import base parameters but don't
# want to depend on //bases:build.
foreman.define_rule('dummy')
