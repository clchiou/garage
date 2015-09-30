"""A simple library for modeling domain-specific objects."""

__all__ = [
    'Model',
    'Field',
    'Refs',
]

from collections import ChainMap, OrderedDict, UserDict

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
        if name.startswith('_'):
            raise TypeError('model cannot start with underscore: %r' % name)
        self.name = name
        self.attrs = DerefDict(
            OrderedDict((key, attrs[key]) for key in sorted(attrs)))
        self.fields = OrderedDict((field.name, field) for field in fields)
        self.a = DictAsAttrs(self.attrs)
        self.f = DictAsAttrs(self.fields)

    def __iter__(self):
        return iter(self.fields.values())

    def field(self, name, **attrs):
        field = Field(name, **attrs)
        self.fields[field.name] = field
        return self


class Field:

    def __init__(self, name, **attrs):
        if name.startswith('_'):
            raise TypeError('field cannot start with underscore: %r' % name)
        self.name = name
        self.attrs = DerefDict(
            OrderedDict((key, attrs[key]) for key in sorted(attrs)))
        self.a = DictAsAttrs(self.attrs)


class DerefDict(UserDict):

    def __init__(self, data):
        super().__init__()
        self.data = data

    def __getitem__(self, key):
        value = super().__getitem__(key)
        if isinstance(value, Refs.Ref):
            value = value.deref()
        return value


class Refs:

    class Ref:

        def __init__(self, refs, name):
            self.refs = refs
            self.name = name

        def deref(self):
            names = self.name.split('.')
            try:
                value = self.refs.context[names[0]]
            except KeyError:
                raise AttributeError(
                    'cannot find variable %r (part of %r) in context %r' %
                    (names[0], self.name, self.refs.context))
            for name in names[1:]:
                value = getattr(value, name)
            return value

    def __init__(self):
        self._context = ChainMap()

    @property
    def context(self):
        return self._context

    def __enter__(self):
        self._context.maps.insert(0, {})
        return self._context

    def __exit__(self, *_):
        self._context.maps.pop(0)

    def ref(self, name):
        return Refs.Ref(self, name)
