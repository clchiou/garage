"""Build http2."""

from shipyard import py


PATH = 'py/http2'


py.define_package(
    package_name='http2',
    derive_src_path=lambda ps: ps['//base:root'] / PATH,
    derive_build_src_path=lambda ps: ps['//base:build'] / PATH,
    build_rule_deps=[
        '//cc/nghttp2:build',
        '//py/cpython:install_cython',
    ],
    tapeout_rule_deps=[
        '//cc/nghttp2:tapeout',
    ],
)
