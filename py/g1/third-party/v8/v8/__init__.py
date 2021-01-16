__all__ = [
    'Array',
    'Context',
    'GlobalContext',
    'HandleScope',
    'Isolate',
    'JavaScriptError',
    'Object',
    'Script',
    'UNDEFINED',
    'UndefinedType',
    'Value',
    'from_python',
    'to_python',
    'run',
    'shutdown',
]

import atexit
import collections.abc
import logging

# Disable warning as pylint cannot infer native extension.
# pylint: disable=no-name-in-module

from ._v8 import initialize as _initialize

# Re-export these.
from ._v8 import Array
from ._v8 import Context
from ._v8 import GlobalContext
from ._v8 import HandleScope
from ._v8 import Isolate
from ._v8 import Object
from ._v8 import Script
from ._v8 import UNDEFINED
from ._v8 import UndefinedType
from ._v8 import Value
from ._v8 import shutdown

logging.getLogger(__name__).addHandler(logging.NullHandler())

_PRIMITIVE_TYPES = (UndefinedType, type(None), bool, int, float, str)


class JavaScriptError(Exception):
    pass


def run(context, code, name='<main>'):
    script = Script(context, name, code)
    return script.run(context)


def from_python(context, py_obj):
    """Python-to-JavaScript recursive converter.

    This will be trapped in an infinite loop if there are self
    references.
    """
    # NOTE: str is a sub-class of collections.abc.Sequence, and so you
    # MUST check _PRIMITIVE_TYPES before collections.abc.Sequence.
    if isinstance(py_obj, _PRIMITIVE_TYPES):
        return py_obj
    elif isinstance(py_obj, collections.abc.Sequence):
        output = Array(context)
        for item in py_obj:
            output.append(from_python(context, item))
        return output
    elif isinstance(py_obj, collections.abc.Mapping):
        output = Object(context)
        for key, value in py_obj.items():
            if not isinstance(key, str):
                raise TypeError('expect str key: {!r}'.format(key))
            output[key] = from_python(context, value)
        return output
    else:
        raise TypeError('unsupported type: {!r}'.format(py_obj))


def to_python(
    js_obj,
    *,
    sequence_type=list,
    undefined_to_none=True,
):
    """JavaScript-to-Python recursive converter.

    This will be trapped in an infinite loop if there are self
    references.
    """

    def convert(x):
        if x is UNDEFINED and undefined_to_none:
            return None
        elif isinstance(x, _PRIMITIVE_TYPES):
            return x
        elif isinstance(x, Array):
            return sequence_type(map(convert, x))
        elif isinstance(x, Object):
            return {key: convert(x[key]) for key in x}
        else:
            raise TypeError('unsupported type: {!r}'.format(x))

    return convert(js_obj)


_initialize(JavaScriptError)
# Is it really necessary to call shutdown on process exit?
atexit.register(shutdown)
