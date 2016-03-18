"""
Schema for object trees that may translate an object tree to composition
of dict and list (this operation is called lower) and translate it back
to object tree (which is called higher).

You may use this as an intermediate layer between your domain object and
network presentation (say, JSON).
"""

__all__ = [
    # Means of combination.
    'Dict',
    'List',
    'Set',
    'Record',
    # Means of primitive.
    'Primitive',
]

from collections import OrderedDict, namedtuple

from garage import asserts


class Record:

    class Name:
        """Annotate the name of this record."""
        def __init__(self, name):
            self.name = name

    class Optional:
        """Annotate an optional field."""
        def __init__(self, name, type_):
            self.name = name
            self.type_ = type_

    class Either:
        """Annotate an exclusive group of fields."""
        def __init__(self, *field_list):
            asserts.precond(len(field_list) > 1)
            self.field_list = field_list

    def __init__(self, *decls):
        self.name = 'Record'
        self.fields = OrderedDict()
        self.optionals = set()
        self.eithers = set()
        self.groups = []

        for decl in decls:
            if isinstance(decl, Record.Name):
                self.name = decl.name
                continue
            elif isinstance(decl, Record.Optional):
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

        self._record = namedtuple(self.name, self.fields)

    def make(self, **kwargs):
        for name in self.fields:
            kwargs.setdefault(name, None)
        return self._record(**kwargs)

    def _check_exclusive(self, rdict):
        for group in self.groups:
            match = 0
            for name in group:
                if name in rdict:
                    match += 1
                    if match > 1:
                        break
            if match != 1:
                raise ValueError('%r of %s are exclusive: %r' %
                                 (group, self.name, rdict))

    def lower(self, record):
        rdict = {}
        for name, type_ in self.fields.items():
            value = getattr(record, name, None)
            if name in self.eithers:
                # "either" is special, we lower empty value, too.
                if value is not None:
                    rdict[name] = type_.lower(value)
            elif Collection.is_collection(type_):
                if value:  # Only lower non-empty value.
                    rdict[name] = type_.lower(value)
            elif name in self.optionals:
                if value is not None:
                    rdict[name] = type_.lower(value)
            elif value is not None:
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
            elif Collection.is_collection(type_):
                values.append(type_.unit())
            elif name in self.eithers:
                values.append(None)
            elif name in self.optionals:
                values.append(None)
            else:
                raise ValueError('%r is required in %s: %r' %
                                 (name, self.name, rdict))
        return self._record._make(values)


class Collection:

    @staticmethod
    def is_collection(type_):
        return (isinstance(type_, Collection) or
                (isinstance(type_, type) and issubclass(type_, Collection)))


class Dict(Collection):

    @staticmethod
    def unit():
        return {}

    @staticmethod
    def lower(value):
        if not isinstance(value, dict):
            raise ValueError('not %r typed: %r' % (dict, value))
        return value

    @staticmethod
    def higher(value):
        if not isinstance(value, dict):
            raise ValueError('not %r typed: %r' % (dict, value))
        return value


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

    @classmethod
    def of_enum(cls, enum_type):

        def lower(member):
            if not isinstance(member, enum_type):
                raise ValueError('not member of %r: %r' % (enum_type, member))
            return member.value

        def higher(value):
            return enum_type(value)

        return cls(lower, higher)

    def __init__(self, lower, higher):
        self.lower = lower
        self.higher = higher
