from templates import common, py


#
# PyYAML official release is too far behind the current head and cannot
# be built in Python 3.7.
#


common.define_git_repo(
    repo='https://github.com/yaml/pyyaml.git',
    treeish='b6cbfeec35e019734263a8f4e6a3340e94fe0a4f',
)


common.define_distro_packages(['libyaml-dev'])


rules = py.define_source_package(
    package='PyYAML',
    patterns=[
        'yaml',
        '_yaml.*.so',  # Extension library
    ],
)
rules.build.depend('git_clone')
rules.build.depend('install_packages')
