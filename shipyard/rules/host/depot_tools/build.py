from foreman import get_relpath, rule

from garage import scripts

from templates import common


# Use master branch at the moment
common.define_git_repo(
    repo='https://chromium.googlesource.com/chromium/tools/depot_tools.git',
)


# depot_tools needs Python 2
common.define_distro_packages(['python'])


@rule
@rule.depend('//base:build')
@rule.depend('install_packages')
@rule.depend('git_clone')
def install(parameters):
    scripts.insert_path(parameters['//base:drydock'] / get_relpath())
