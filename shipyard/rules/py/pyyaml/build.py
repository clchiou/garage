from templates import py


py.define_pip_package(
    package='PyYAML',
    version='3.12',
    distro_packages=[
        'libyaml-dev',
    ],
    patterns=[
        'yaml',
        '_yaml.*.so',  # Extension library
    ],
)
