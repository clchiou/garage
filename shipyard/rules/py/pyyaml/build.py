from templates import common, py


common.define_distro_packages(['libyaml-dev'])


rules = py.define_pip_package(
    package='PyYAML',
    version='3.12',
    patterns=[
        'yaml',
        '_yaml.*.so',  # Extension library
    ],
)
rules.build.depend('install_packages')
