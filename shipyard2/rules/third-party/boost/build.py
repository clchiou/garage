"""Build Boost from source."""

import json
import logging
from pathlib import Path

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT

import shipyard2.rules.bases

LOG = logging.getLogger(__name__)

shipyard2.rules.bases.define_git_repo(
    'https://github.com/boostorg/boost.git',
    'boost-1.77.0',
)

(foreman.define_parameter.list_typed('libraries')\
 .with_doc('select boost libraries to build'))

shipyard2.rules.bases.define_distro_packages([
    'g++',
    'libstdc++-8-dev',
])


# Add `REMOVE` so that parameters are not passed from `config` to the
# dependent rules.
@foreman.rule
@foreman.rule.depend('//bases:build', parameters=foreman.REMOVE)
@foreman.rule.depend(
    '//third-party/cpython:build',
    when=lambda ps: 'python' in (ps['libraries'] or ()),
    parameters=foreman.REMOVE,
)
def config(parameters):
    config_path = _get_config_path(parameters)
    scripts.mkdir(config_path.parent)
    config_path.write_text(
        json.dumps({
            'libraries':
            sorted(ASSERT.not_empty(parameters['libraries'])),
        })
    )


# NOTE: `build` should not depend on parameter-less `config` since it
# does not know which libraries to build (yet).
@foreman.rule
@foreman.rule.depend('git-clone')
@foreman.rule.depend('install')
def build(parameters):
    config_data = json.loads(
        ASSERT.predicate(_get_config_path(parameters), Path.is_file)\
        .read_text()
    )
    src_path = parameters['//bases:drydock'] / foreman.get_relpath()
    src_path /= src_path.name
    with scripts.using_cwd(src_path):
        _build(parameters, src_path, config_data)
        _install()


def _get_config_path(ps):
    return ps['//bases:drydock'] / foreman.get_relpath() / 'config.json'


def _build(parameters, src_path, config_data):
    libraries = ASSERT.getitem(config_data, 'libraries')
    if (src_path / 'stage').exists():
        LOG.info('skip: build boost: %s', libraries)
        return
    LOG.info('build boost: %s', libraries)
    scripts.run([
        './bootstrap.sh',
        '--with-libraries=%s' % ','.join(libraries),
        *(('--with-python=%s' % parameters['//third-party/cpython:python'], )
          if 'python' in libraries else ()),
        'variant=release',
        'link=shared',
        'threading=multi',
    ])
    scripts.run(['./b2', 'stage'])


def _install():
    if Path('/usr/local/include/boost').exists():
        LOG.info('skip: install boost')
        return
    LOG.info('install boost')
    with scripts.using_sudo():
        scripts.run(['./b2', 'install'])
        scripts.run(['ldconfig'])
