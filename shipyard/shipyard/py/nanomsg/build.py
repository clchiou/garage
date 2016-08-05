"""Build nanomsg Python binding."""

from shipyard import py


PATH = 'py/nanomsg'


py.define_package(
    package_name='nanomsg',
    derive_src_path=lambda ps: ps['//base:root'] / PATH,
    derive_build_src_path=lambda ps: ps['//base:build'] / PATH,
    build_rule_deps=['//cc/nanomsg:build'],
    tapeout_rule_deps=['//cc/nanomsg:tapeout'],
)