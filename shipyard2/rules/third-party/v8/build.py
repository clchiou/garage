"""Build v8 from source."""

import logging

import foreman

from g1 import scripts
from g1.bases.assertions import ASSERT

import shipyard2.rules.bases

LOG = logging.getLogger(__name__)

# Find the current releases here: https://omahaproxy.appspot.com/
# We choose stable Chrome version in the table.  The v8_version column
# can be found at the right of the same row, and the first two digits
# are the branch-head.
(foreman.define_parameter('branch-head')\
 .with_type(str)
 .with_default('9.4'))

# Do NOT use `./build/install-build-deps.sh` to install dependencies as
# it installs dependencies for Chrome, not just for V8.
shipyard2.rules.bases.define_distro_packages([
    'g++',
    'libc6-dev',
    'libglib2.0-dev',
    'libicu-dev',
    # Sadly, some v8 scripts still use unversioned `python`.
    'python-is-python3',
])


@foreman.rule
@foreman.rule.depend('//bases:build')
@foreman.rule.depend('//third-party/depot_tools:build')
@foreman.rule.depend('install')
def build(parameters):
    src_path = _get_src_path(parameters)
    ASSERT.equal(src_path.name, 'v8')
    _fetch(parameters, src_path)
    _build(src_path)


@foreman.rule
def austerity(parameters):
    with scripts.using_sudo():
        for path in _get_src_path(parameters).iterdir():
            if path.name not in ('include', 'out.gn'):
                scripts.rm(path, recursive=True)


def _get_src_path(parameters):
    src_parent_path = parameters['//bases:drydock'] / foreman.get_relpath()
    return src_parent_path / src_parent_path.name


def _fetch(parameters, src_path):
    if src_path.exists():
        LOG.info('skip: fetch v8')
        return
    LOG.info('fetch v8')
    scripts.mkdir(src_path.parent)
    with scripts.using_cwd(src_path.parent):
        scripts.run(['fetch', 'v8'])
    branch = 'branch-heads/%s' % parameters['branch-head']
    with scripts.using_cwd(src_path):
        scripts.run(['git', 'checkout', branch])
        scripts.run(['git', 'pull', 'origin', branch])
        scripts.run(['gclient', 'sync'])


def _build(src_path):
    if (src_path / 'out.gn/x64.release/obj/libv8_monolith.a').exists():
        LOG.info('skip: build v8')
        return
    LOG.info('build v8')
    with scripts.using_cwd(src_path):
        _fixup()
        scripts.run([
            './tools/dev/v8gen.py',
            'gen',
            # x64.release.sample sets v8_monolithic=true.
            *('-b', 'x64.release.sample'),
            # Remove ".sample" from output directory.
            'x64.release',
        ])
        scripts.run(['ninja', '-C', 'out.gn/x64.release', 'v8_monolith'])


def _fixup():
    # TODO: Patch some scripts for Python 3.10.  Remove this after
    # upstream fixes it.
    scripts.run([
        'sed',
        '--in-place',
        '--regexp-extended',
        r's/(from\s+collections)\s+(import\s+Mapping)/\1.abc \2/',
        'third_party/jinja2/tests.py',
    ])
