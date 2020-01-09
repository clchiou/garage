"""Build nng from source."""

import logging

import foreman

from g1 import scripts

import shipyard2.rules.bases

LOG = logging.getLogger(__name__)

shipyard2.rules.bases.define_git_repo(
    'https://github.com/nanomsg/nng.git',
    'v1.2.3',
)

shipyard2.rules.bases.define_distro_packages([
    'cmake',
    'gcc',
    'g++',
    'ninja-build',
])


@foreman.rule
@foreman.rule.depend('//bases:build')
@foreman.rule.depend('git-clone')
@foreman.rule.depend('install')
def build(parameters):
    src_path = parameters['//bases:drydock'] / foreman.get_relpath()
    build_dir_path = src_path / 'build'
    if build_dir_path.exists():
        LOG.info('skip: build nng')
        return
    LOG.info('build nng')
    scripts.mkdir(build_dir_path)
    with scripts.using_cwd(build_dir_path):
        scripts.run([
            'cmake',
            *('-D', 'BUILD_SHARED_LIBS:BOOL=ON'),
            *('-G', 'Ninja'),
            '..',
        ])
        scripts.run(['ninja'])
        # Skip `ninja test` for now.
        with scripts.using_sudo():
            scripts.run(['ninja', 'install'])
            scripts.run(['ldconfig'])
