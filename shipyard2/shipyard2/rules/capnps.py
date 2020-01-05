"""Helpers for writing rules that depends on //py/g1/third-party/capnp."""

__all__ = [
    'make_global_options',
]


def make_global_options(ps):
    return [
        'compile_schemas',
        *('--import-path=%s/codex' % path for path in ps['//bases:roots']),
    ]
