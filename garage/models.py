"""A simple library for modeling domain-specific objects."""

__all__ = [
    'Model',
    'Field',
    'Ref',
]

from collections import OrderedDict
from collections import namedtuple
from functools import partialmethod

from garage.collections import DictAsAttrs


class Model:
    """A model describes domain-specific objects.  It is basically an
       ordered collection of fields.

       We intend to support duck typing, which means that domain objects
       are not necessarily of the same class, and thus a model is not a
       class object for creating domain objects.

       Instead, you use a model as a blueprint (or a meta class, if you
       will) for creating class objects that in turn will create domain
       objects.
    """

    def __init__(self, name, *fields, **attrs):
        self.name = name
        self.attrs = OrderedDict((key, attrs[key]) for key in sorted(attrs))
        self.fields = OrderedDict((field.name, field) for field in fields)
        self.a = DictAsAttrs(self.attrs)
        self.f = DictAsAttrs(self.fields)

    def __iter__(self):
        return iter(self.fields.values())

    def field(self, name, **attrs):
        field = Field(name, **attrs)
        self.fields[field.name] = field
        return self

    def make_namedtuple(self, name=None):
        return namedtuple(name or self.name, [field.name for field in self])

    def make_builder(self, name=None, bases=(), build=None):
        namespace = self._make_builder_namespace(self, build)
        return type(name or self.name, bases, namespace)

    @staticmethod
    def _make_builder_namespace(model, build):

        data = {}

        def __init__(_, obj=None):
            if obj:
                for field in model:
                    data[field.name] = getattr(obj, field.name)

        def __call__(_, **more_data):
            data.update(more_data)
            if build:
                return build(**data)
            else:
                return OrderedDict(
                    (field.name, data[field.name]) for field in model)

        def setter(self, name, value):
            data[name] = value
            return self

        namespace = {
            field.name: partialmethod(setter, field.name) for field in model
        }
        namespace['__init__'] = __init__
        namespace['__call__'] = __call__

        return namespace


class Field:

    def __init__(self, name, **attrs):
        if name.startswith('_'):
            raise TypeError('field cannot start with underscore: %r' % name)
        self.name = name
        self.attrs = OrderedDict((key, attrs[key]) for key in sorted(attrs))
        self.a = DictAsAttrs(self.attrs)

    def get_attr_as_pair(self, obj):
        return (self.name, getattr(obj, self.name))


class Ref:

    def __init__(self, name):
        self.name = name

    def deref(self, context):
        names = self.name.split('.')
        try:
            value = context[names[0]]
        except KeyError:
            raise AttributeError(
                'cannot find variable %r (part of %r) in context %r' %
                (names[0], self.name, context))
        for name in names[1:]:
            value = getattr(value, name)
        return value
