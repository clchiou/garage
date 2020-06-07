"""Build capnproto from source."""

import logging

import foreman

from g1 import scripts

import shipyard2.rules.bases

LOG = logging.getLogger(__name__)

shipyard2.rules.bases.define_git_repo(
    'https://github.com/capnproto/capnproto.git',
    'v0.7.0',
)

shipyard2.rules.bases.define_distro_packages([
    'autoconf',
    'automake',
    'g++',
    'libtool',
    'pkg-config',
])


@foreman.rule
@foreman.rule.depend('//bases:build')
@foreman.rule.depend('git-clone')
@foreman.rule.depend('install')
def build(parameters):
    src_path = parameters['//bases:drydock'] / foreman.get_relpath()
    src_path /= src_path.name
    if (src_path / 'c++/.libs/libcapnp.so').exists():
        LOG.info('skip: build capnproto')
        return
    LOG.info('build capnproto')
    with scripts.using_cwd(src_path / 'c++'):
        scripts.run(['autoreconf', '-i'])
        scripts.run(['./configure'])
        # Skip `make check` for now.
        scripts.run(['make'])
        with scripts.using_sudo():
            scripts.run(['make', 'install'])
            scripts.run(['ldconfig'])
