"""Build startup."""

from pathlib import Path

from shipyard import py


py.define_package(
    package_name='startup',
    derive_src_path=lambda ps: Path.home() / 'startup',
    derive_build_src_path=lambda ps: ps['//base:build'] / 'py/startup',
)
