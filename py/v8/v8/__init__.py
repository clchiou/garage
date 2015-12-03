__all__ = [
    'V8',
]

import logging
from collections import Mapping, OrderedDict
from contextlib import ExitStack

from ._v8 import V8 as _V8
from ._v8.utils import not_null
from ._v8.values import (
    Array,
    Script,
    String,
    Value,
)


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


# TODO: Make Context a MutableMapping
class Context(Mapping):

    def __init__(self, isolate):
        self.isolate = isolate
        self._exit_stack = None
        self.handle_scope = None
        self.context = None
        self.vars = None

    def __enter__(self):
        self._exit_stack = ExitStack()
        self._exit_stack.__enter__()
        scoped = make_scoped(self._exit_stack)
        self.handle_scope = scoped(self.isolate.isolate.handle_scope())
        self.context = scoped(self.isolate.isolate.context())
        self.vars = scoped(self.context.vars())
        self._exit_stack.enter_context(self.context)
        return self

    def __exit__(self, *exc_details):
        self._exit_stack.__exit__(*exc_details)
        del self.vars
        del self.context
        del self.handle_scope
        del self._exit_stack

    def execute(self, source):
        with ExitStack() as stack:
            scoped = make_scoped(stack)
            source = scoped(String.from_str(source, self.isolate.isolate))
            script = scoped(Script.compile(self.context, source))
            return translate(scoped(script.run()), self.context)

    def __contains__(self, name):
        with ExitStack() as stack:
            scoped = make_scoped(stack)
            name_string = scoped(String.from_str(name, self.isolate.isolate))
            name_value = scoped(Value.from_string(name_string))
            return self.vars.has_prop(name_value)

    def __getitem__(self, name):
        with ExitStack() as stack:
            scoped = make_scoped(stack)
            name_string = scoped(String.from_str(name, self.isolate.isolate))
            name_value = scoped(Value.from_string(name_string))
            try:
                value = scoped(self.vars.get_prop(name_value))
            except AttributeError:
                raise KeyError(name)
            return translate(value, self.context)

    def __len__(self):
        with ExitStack() as stack:
            scoped = make_scoped(stack)
            return len(scoped(self.vars.get_property_names()))

    def __iter__(self):
        with ExitStack() as stack:
            scoped = make_scoped(stack)
            names = scoped(self.vars.get_property_names())
            for name in map(scoped, names):
                yield name.as_str()


class JavaScript:
    """A JavaScript object that cannot be translated into a Python object."""

    def __init__(self, value):
        self.js_repr = str(value)

    def __str__(self):
        return 'JavaScript([%s])' % self.js_repr

    def __repr__(self):
        return 'JavaScript([%s])' % self.js_repr


def translate(value, context):
    if value.is_null():
        return None
    elif value.is_true():
        return True
    elif value.is_false():
        return False
    elif value.is_array():
        with ExitStack() as stack:
            scoped = make_scoped(stack)
            array = scoped(value.as_array(context))
            return [translate(v, context) for v in map(scoped, array)]
    elif value.is_map():
        with ExitStack() as stack:
            scoped = make_scoped(stack)
            kv_list = scoped(scoped(value.as_map(context)).as_array())
            return OrderedDict(
                (
                    translate(scoped(kv_list[i]), context),
                    translate(scoped(kv_list[i + 1]), context),
                )
                for i in range(0, len(kv_list), 2)
            )
    elif value.is_string():
        return value.as_str()
    elif value.is_number():
        if value.is_int32() or value.is_uint32():
            return value.as_int()
        else:
            return value.as_float()
    elif is_just_object(value):
        with ExitStack() as stack:
            scoped = make_scoped(stack)
            object_ = scoped(value.as_object(context))
            names = scoped(object_.get_property_names())
            return {
                translate(name, context):
                    translate(scoped(object_.get_prop(name)), context)
                for name in map(scoped, names)
            }
    else:
        return JavaScript(value)


def is_just_object(value):
    # TODO: This is brittle. Fix this!
    return value.is_object() and not (
        value.is_array() or
        value.is_array_buffer() or
        value.is_array_buffer_view() or
        value.is_shared_array_buffer() or
        value.is_date() or
        value.is_function() or
        value.is_map() or
        value.is_promise() or
        value.is_regexp() or
        value.is_set() or
        value.is_string() or
        value.is_boolean_object() or
        value.is_number_object() or
        value.is_string_object() or
        value.is_symbol_object()
    )


def make_scoped(exit_stack):
    def scoped(var):
        exit_stack.callback(var.close)
        return var
    return scoped
