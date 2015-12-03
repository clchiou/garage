__all__ = [
    'from_js',
    'make_scoped',
    'not_null',
]

from garage import asserts


class JsObject:
    """A JavaScript object that cannot be translated into a Python object."""

    def __init__(self, value):
        self.js_repr = str(value)

    def __str__(self):
        return 'JsObject([%s])' % self.js_repr

    def __repr__(self):
        return 'JsObject([%s])' % self.js_repr


def from_js(value, context):
    if value.is_array():
        array = value.as_array(context)
        try:
            return [from_js(element, context) for element in array]
        finally:
            array.close()
    elif value.is_string():
        return value.as_str()
    elif value.is_number():
        if value.is_int32() or value.is_uint32():
            return value.as_int()
        else:
            return value.as_float()
    else:
        return JsObject(value)


def make_scoped(exit_stack):
    def scoped(var):
        exit_stack.callback(var.close)
        return var
    return scoped


def not_null(value):
    asserts.precond(value is not None)
    return value
