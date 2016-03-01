"""
Schema for object trees that may translate an object tree to composition
of dict and list (this operation is called lower) and translate it back
to object tree (which is called higher).

You may use this as an intermediate layer between your domain object and
network presentation (say, JSON).
"""

__all__ = [
    # Means of combination.
    'Either',
    'List',
    'Record',
    'Set',
    # Means of primitive.
    'Primitive',
]

from collections import namedtuple

from garage import asserts


class Record:

    class Optional:
        """Annotate an optional field."""
        def __init__(self, type_):
            self.type_ = type_

    def __init__(self, name, fields):
        self.name = name
        self.fields = fields
        self._make_record = namedtuple(name, self.fields.keys())

    def lower(self, record):
        rdict = {}
        for field_name, field_type in self.fields.items():
            field_value = getattr(record, field_name, None)
            if isinstance(field_type, Record.Optional):
                if field_value is None:
                    continue
                else:
                    field_type = field_type.type_
            elif isinstance(field_type, Collection):
                if not field_value:
                    continue
            elif field_value is None:
                raise ValueError('%r is required in %s: %r' %
                                 (field_name, self.name, record))
            rdict[field_name] = field_type.lower(field_value)
        return rdict

    def higher(self, rdict):
        fields = {}
        for field_name, field_type in self.fields.items():
            value = rdict.get(field_name)
            if isinstance(field_type, Record.Optional):
                if value is None:
                    fields[field_name] = None
                    continue
                else:
                    field_type = field_type.type_
            elif isinstance(field_type, Collection):
                if not value:
                    fields[field_name] = field_type.unit()
                    continue
            elif value is None:
                raise ValueError('%r is required in %s: %r' %
                                 (field_name, self.name, rdict))
            fields[field_name] = field_type.higher(value)
        return self._make_record(**fields)


class Either:

    def __init__(self, choices):
        asserts.precond(len(choices) > 1)
        self.choices = choices
        name = 'Either__%s' % '_'.join(choices)
        self._make_either = namedtuple(name, self.choices.keys())

    def lower_choice(self, choice_name, value):
        if choice_name not in self.choices:
            raise ValueError('no matching choice: %r' % choice_name)
        return {choice_name: self.choices[choice_name].lower(value)}

    def lower(self, either):
        edict = {}
        for choice_name, choice_type in self.choices.items():
            value = getattr(either, choice_name, None)
            if value is not None:
                edict[choice_name] = choice_type.lower(value)
        if len(edict) != 1:
            raise ValueError('must choose exactly one: %r' % either)
        return edict

    def higher(self, edict):
        if len(edict) != 1:
            raise ValueError('must choose exactly one: %r' % edict)
        choice_name, value = next(iter(edict.items()))
        if choice_name not in self.choices:
            raise ValueError('no matching choice: %r' % edict)
        choices = {name: None for name in self.choices}
        choices[choice_name] = self.choices[choice_name].higher(value)
        return self._make_either(**choices)


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
