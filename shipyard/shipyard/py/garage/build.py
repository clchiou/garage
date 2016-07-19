"""Build garage."""

from shipyard import py


PATH = 'py/garage'


py.define_package(
    package_name='garage',
    derive_src_path=lambda ps: ps['//base:root'] / PATH,
    derive_build_src_path=lambda ps: ps['//base:build'] / PATH,
)
