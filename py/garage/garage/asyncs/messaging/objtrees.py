"""
Schema for object trees that may translate an object tree to composition
of dict and list (this operation is called lower) and translate it back
to object tree (which is called higher).

You may use this as an intermediate layer between your domain object and
network presentation (say, JSON).
"""

__all__ = [
    # Means of combination.
    'List',
    'Set',
    'Record',
    # Means of primitive.
    'Primitive',
]

from collections import OrderedDict, namedtuple

from garage import asserts


class Record:

    class Optional:
        """Annotate an optional field."""
        def __init__(self, name, type_):
            self.name = name
            self.type_ = type_

    class Either:
        """Annotate an exclusive group of fields."""
        def __init__(self, field_list):
            asserts.precond(len(field_list) > 1)
            self.field_list = field_list

    def __init__(self, name, decls):
        self.name = name

        self.fields = OrderedDict()
        self.optionals = set()
        self.eithers = set()
        self.groups = []

        for decl in decls:
            if isinstance(decl, Record.Optional):
                self.fields[decl.name] = decl.type_
                self.optionals.add(decl.name)
            elif isinstance(decl, Record.Either):
                group = set()
                for name, type_ in decl.field_list:
                    self.fields[name] = type_
                    self.eithers.add(name)
                    group.add(name)
                self.groups.append(group)
            else:
                name, type_ = decl
                self.fields[name] = type_

        self.record = namedtuple(name, self.fields)

    def _check_exclusive(self, rdict):
        for group in self.groups:
            match = 0
            for name in group:
                if name in rdict:
                    match += 1
                    if match > 1:
                        break
            if match != 1:
                raise ValueError('%r are exclusive in %s: %r' %
                                 (group, self.name, rdict))

    def lower(self, record):
        rdict = {}
        for name, type_ in self.fields.items():
            value = getattr(record, name, None)
            if value:  # Lower non-empty value.
                rdict[name] = type_.lower(value)
            elif name in self.eithers:
                # "either" is special, we lower empty value, too.
                if value is not None:
                    rdict[name] = type_.lower(value)
            elif isinstance(type_, Collection):
                if value:  # Only lower non-empty value.
                    rdict[name] = type_.lower(value)
            elif name in self.optionals:
                if value is not None:
                    rdict[name] = type_.lower(value)
            else:
                raise ValueError('%r is required in %s: %r' %
                                 (name, self.name, record))
        self._check_exclusive(rdict)
        return rdict

    def higher(self, rdict):
        self._check_exclusive(rdict)
        values = []
        for name, type_ in self.fields.items():
            value = rdict.get(name)
            if value is not None:
                values.append(type_.higher(value))
            elif isinstance(type_, Collection):
                values.append(type_.unit())
            elif name in self.eithers:
                values.append(None)
            elif name in self.optionals:
                values.append(None)
            else:
                raise ValueError('%r is required in %s: %r' %
                                 (name, self.name, rdict))
        return self.record._make(values)


class Collection:
    pass


class List(Collection):

    @staticmethod
    def unit():
        return ()

    def __init__(self, type_):
        self.type_ = type_

    def lower(self, items):
        return tuple(map(self.type_.lower, items))

    def higher(self, items):
        return tuple(map(self.type_.higher, items))


class Set(Collection):

    @staticmethod
    def unit():
        return frozenset()

    def __init__(self, type_):
        self.type_ = type_

    def lower(self, items):
        # JSON cannot encode set.
        return tuple(map(self.type_.lower, items))

    def higher(self, items):
        return frozenset(map(self.type_.higher, items))


class Primitive:

    @classmethod
    def of_type(cls, type_):

        def lower(value):
            if not isinstance(value, type_):
                raise ValueError('not %r typed: %r' % (type_, value))
            return value

        def higher(value):
            if not isinstance(value, type_):
                raise ValueError('not %r typed: %r' % (type_, value))
            return value

        return cls(lower, higher)

    def __init__(self, lower, higher):
        self.lower = lower
        self.higher = higher
