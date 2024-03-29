"""Install depot_tools."""

import foreman

from g1 import scripts

import shipyard2.rules.bases

shipyard2.rules.bases.define_git_repo(
    'https://chromium.googlesource.com/chromium/tools/depot_tools.git',
    None,  # depot_tools updates itself.
)

shipyard2.rules.bases.define_distro_packages([
    'wget',
    # Sadly, some depot_tools scripts still use unversioned `python`.
    'python-is-python3',
])


@foreman.rule
@foreman.rule.depend('//bases:build')
@foreman.rule.depend('git-clone')
@foreman.rule.depend('install')
def build(parameters):
    src_path = parameters['//bases:drydock'] / foreman.get_relpath()
    src_path /= src_path.name
    scripts.export_path('PATH', src_path)
    with scripts.using_cwd(src_path):
        scripts.run(['gclient'])  # This updates depot_tools.
