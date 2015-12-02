__all__ = [
    'from_js',
    'make_scoped',
    'not_null',
]

from garage import asserts


def from_js(value):
    if value.is_string():
        return str(value)
    else:
        asserts.fail('cannot translate for this JavaScript type')


def make_scoped(exit_stack):
    def scoped(var):
        exit_stack.callback(var.close)
        return var
    return scoped


def not_null(value):
    asserts.precond(value is not None)
    return value
