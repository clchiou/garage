__all__ = [
    'V8',
]

import logging
from contextlib import ExitStack

from ._v8 import V8 as _V8
from ._v8.utils import not_null
from ._v8.values import Script, String


logging.getLogger(__name__).addHandler(logging.NullHandler())


class V8:

    def __init__(self, natives_blob_path, snapshot_blob_path):
        self.natives_blob_path = natives_blob_path
        self.snapshot_blob_path = snapshot_blob_path
        self.v8 = None

    def __enter__(self):
        self.v8 = _V8(self.natives_blob_path, self.snapshot_blob_path)
        return self

    def __exit__(self, *_):
        self.v8.close()
        del self.v8

    def isolate(self):
        return Isolate(self)


class Isolate:

    def __init__(self, v8):
        self.v8 = v8
        self._exit_stack = None
        self.isolate = None

    def __enter__(self):
        self._exit_stack = ExitStack()
        self._exit_stack.__enter__()
        self.isolate = self.v8.v8.isolate()
        self._exit_stack.callback(self.isolate.close)
        self._exit_stack.enter_context(self.isolate)
        return self

    def __exit__(self, *exc_details):
        self._exit_stack.__exit__(*exc_details)
        del self.isolate
        del self._exit_stack

    def context(self):
        return Context(self)


class Context:

    def __init__(self, isolate):
        self.isolate = isolate
        self._exit_stack = None
        self.handle_scope = None
        self.context = None

    def __enter__(self):
        self._exit_stack = ExitStack()
        self._exit_stack.__enter__()
        self.handle_scope = self.isolate.isolate.handle_scope()
        self._exit_stack.callback(self.handle_scope.close)
        self.context = self.isolate.isolate.context()
        self._exit_stack.callback(self.context.close)
        self._exit_stack.enter_context(self.context)
        return self

    def __exit__(self, *exc_details):
        self._exit_stack.__exit__(*exc_details)
        del self.context
        del self.handle_scope
        del self._exit_stack

    def execute(self, source):
        with ExitStack() as stack:
            def scoped(var):
                stack.callback(var.close)
                return var
            source = scoped(String.from_str(source, self.isolate.isolate))
            script = scoped(Script.compile(self.context, source))
            return translate(scoped(script.run()), self.context)


class JsObject:
    """A JavaScript object that cannot be translated into a Python object."""

    def __init__(self, value):
        self.js_repr = str(value)

    def __str__(self):
        return 'JsObject([%s])' % self.js_repr

    def __repr__(self):
        return 'JsObject([%s])' % self.js_repr


def translate(value, context):
    if value.is_array():
        array = value.as_array(context)
        try:
            return [translate(element, context) for element in array]
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
