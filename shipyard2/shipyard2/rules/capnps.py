"""Helpers for writing rules that depends on //python/g1/third-party/capnp."""

__all__ = [
    'make_global_options',
]


def make_global_options(ps):
    return [
        'compile_schemas',
        '--import-path=%s' %
        ':'.join(str(path / 'codex') for path in ps['//bases:roots']),
    ]
