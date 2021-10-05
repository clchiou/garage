"""Build nghttp2 from source."""

import logging

import foreman

from g1 import scripts

import shipyard2.rules.bases

LOG = logging.getLogger(__name__)

shipyard2.rules.bases.define_git_repo(
    'https://github.com/nghttp2/nghttp2.git',
    'v1.45.1',
)

shipyard2.rules.bases.define_distro_packages([
    'autoconf',
    'automake',
    'autotools-dev',
    'binutils',
    'cython',
    'g++',
    'libc-ares-dev',
    'libcunit1-dev',
    'libev-dev',
    'libevent-dev',
    'libjansson-dev',
    'libjemalloc-dev',
    'libssl-dev',
    'libsystemd-dev',
    'libtool',
    'libxml2-dev',
    'make',
    'pkg-config',
    'python3-dev',
    'python-setuptools',
    'zlib1g-dev',
])


@foreman.rule
@foreman.rule.depend('//bases:build')
@foreman.rule.depend('git-clone')
@foreman.rule.depend('install')
def build(parameters):
    src_path = parameters['//bases:drydock'] / foreman.get_relpath()
    src_path /= src_path.name
    if (src_path / 'lib/.libs/libnghttp2.so').exists():
        LOG.info('skip: build nghttp2')
        return
    LOG.info('build nghttp2')
    with scripts.using_cwd(src_path):
        scripts.run(['autoreconf', '-i'])
        scripts.run(['automake'])
        scripts.run(['autoconf'])
        scripts.run(['./configure'])
        scripts.run(['make'])
        with scripts.using_sudo():
            scripts.run(['make', 'install'])
            scripts.run(['ldconfig'])
