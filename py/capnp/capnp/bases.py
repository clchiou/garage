__all__ = [
    'repr_object',
    'str_value',

    'get_schema_id',

    'camel_to_lower_snake',
    'camel_to_upper_snake',
    'snake_to_lower_camel',

    'dicts_get',
]

import re

from . import native


def repr_object(obj):
    """The default __repr__ implementation."""
    cls = obj.__class__
    return (
        '<%s.%s 0x%x %s>' % (cls.__module__, cls.__qualname__, id(obj), obj))


def str_value(value):
    """Format Python value to look like Cap'n Proto textual format."""
    if value is None:
        return 'void'
    elif value is True:
        return 'true'
    elif value is False:
        return 'false'
    elif isinstance(value, str):
        return '"%s"' % value.replace('"', '\\"')
    elif isinstance(value, bytes):
        return '0x"%s"' % ' '.join('%02x' % x for x in value)
    else:
        return str(value)


def get_schema_id(schema):
    if isinstance(schema, native.ListSchema):
        return _get_list_schema_id(schema)
    node = schema.getProto()
    if schema.isBranded():
        return _get_branded_schema_id(schema, node)
    else:
        return schema.getProto().getId()


def _get_branded_schema_id(schema, node):
    node_id = node.getId()
    schema_id = ['g', node_id]
    balist = schema.getBrandArgumentsAtScope(node_id)
    schema_id.extend(balist[i].hashCode() for i in range(balist.size()))
    return tuple(schema_id)


def _get_list_schema_id(schema):
    """Generate an unique id for list schema.

    We cannot call schema.getProto().getId() to generate an unique id
    because ListSchema is different - it is not associated with a Node.
    """
    type_ = schema.getElementType()
    level = 0
    while type_.isList():
        type_ = type_.asList().getElementType()
        level += 1
    return ('l', level, type_.hashCode())


# An upper case word followed a lower case letter.  For now a "word" is
# anything longer than 1 letter.
CAMEL_PATTERN_1 = re.compile(r'([A-Z]{2})([a-z0-9])')
# A lower case letter followed an upper case letter.
CAMEL_PATTERN_2 = re.compile(r'([a-z0-9])([A-Z])')


def _camel_to_snake(camel):
    camel = CAMEL_PATTERN_1.sub(r'\1_\2', camel)
    camel = CAMEL_PATTERN_2.sub(r'\1_\2', camel)
    return camel


def camel_to_upper_snake(camel):
    """Turn a CamelCase or camelCase name into a SNAKE_CASE one."""
    return _camel_to_snake(camel).upper()


def camel_to_lower_snake(camel):
    """Turn a CamelCase or camelCase name into a snake_case one."""
    return _camel_to_snake(camel).lower()


SNAKE_PATTERN = re.compile(r'_([a-z])')


def snake_to_lower_camel(snake):
    """Turn a SNAKE_CASE or snake_case name into camelCase."""
    return SNAKE_PATTERN.sub(lambda s: s.group(1).upper(), snake.lower())


def dicts_get(dicts, key, default=None):
    """Do get() on multiple dict.

    NOTE: While `d1.get(k) or d2.get(k)` looks cool, it is actually
    incorrect because d1 might contain false value (like an empty tuple)
    and you should return that instead of going on to d2.
    """
    for d in dicts:
        try:
            return d[key]
        except KeyError:
            pass
    return default
