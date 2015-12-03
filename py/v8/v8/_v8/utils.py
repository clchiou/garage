__all__ = [
    'not_null',
]

from garage import asserts


def not_null(value):
    asserts.precond(value is not None)
    return value
