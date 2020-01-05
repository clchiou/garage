"""Build capnproto java host tools.

NOTE: Java (runtime) libraries are installed through Gradle.
"""

import logging
from pathlib import Path

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT

import shipyard2.rules.bases

LOG = logging.getLogger(__name__)

shipyard2.rules.bases.define_git_repo(
    'https://github.com/capnproto/capnproto-java.git',
    # v0.1.4 does not use C++14 when compile; let's use a recent version
    # instead.
    '4f514ad1a00e5d351b9840a0aa63cd3cc67e6180',
)

shipyard2.rules.bases.define_distro_packages([
    'g++',
    'pkg-config',
])


@foreman.rule
@foreman.rule.depend('//third-party/capnproto:build')
@foreman.rule.depend('git-clone')
@foreman.rule.depend('install')
def build(parameters):
    src_path = parameters['//bases:drydock'] / foreman.get_relpath()
    if (src_path / 'capnpc-java').exists():
        LOG.info('skip: build capnproto-java')
        return
    LOG.info('build capnproto-java')
    bin_path = _get_var_path('exec_prefix') / 'bin'
    header_path = _get_var_path('includedir') / 'capnp'
    with scripts.using_cwd(src_path):
        scripts.run(['make'])
        with scripts.using_sudo():
            scripts.cp('capnpc-java', bin_path)
            scripts.cp(
                'compiler/src/main/schema/capnp/java.capnp', header_path
            )


def _get_var_path(name):
    with scripts.doing_capture_output():
        proc = scripts.run([
            'pkg-config',
            '--variable=%s' % name,
            'capnp',
        ])
        return ASSERT.predicate(
            Path(proc.stdout.decode('utf8').strip()),
            Path.is_dir,
        )
