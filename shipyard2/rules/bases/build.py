"""Base of application image."""

from pathlib import Path

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT

import shipyard2.rules.bases

(foreman.define_parameter.list_typed('roots')\
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


@foreman.rule
def build(parameters):
    ASSERT.all(parameters['roots'], _is_root_dir)
    scripts.mkdir(parameters['drydock'])


def _is_root_dir(path):
    return (path / '.git').is_dir()
