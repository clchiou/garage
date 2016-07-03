"""Install PyYAML."""

from shipyard import py


py.define_pip_package(
    package_name='PyYAML',
    version='3.11',
    dep_pkgs=[
        'libyaml-dev',
    ],
    dep_libs=[
        'libyaml',  # Match both libyaml-0.so and libyaml.so.
    ],
    patterns=[
        '*yaml*'
    ],
)
