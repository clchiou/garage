"""Build http2."""

from shipyard import py


PATH = 'py/http2'


py.define_package(
    package_name='http2',
    derive_src_path=lambda ps: ps['//base:root'] / PATH,
    derive_build_src_path=lambda ps: ps['//base:build_src'] / PATH,
    build_rule_deps=[
        '//cpython:install_cython',
        '//nghttp2:build',
    ],
)
