__all__ = [
    'repr_object',
    'str_value',

    'list_schema_id',
]

from . import native


def repr_object(obj):
    """The default __repr__ implementation."""
    cls = obj.__class__
    return (
        '<%s.%s 0x%x %s>' % (cls.__module__, cls.__qualname__, id(obj), obj))


def str_value(value):
    """Format Python value to look like Cap'n Proto textual format.

    At the moment they are not identical.
    """
    if value is None:
        return 'void'
    elif value is True:
        return 'true'
    elif value is False:
        return 'false'
    elif isinstance(value, str):
        return repr(value)
    else:
        return str(value)


def list_schema_id(schema):
    """Generate an unique id for list schema.

    We cannot call schema.getProto().getId() to generate an unique id
    because ListSchema is different - it is not associated with a Node.
    """
    assert isinstance(schema, native.ListSchema)
    type_ = schema.getElementType()
    level = 0
    while type_.isList():
        type_ = type_.asList().getElementType()
        level += 1
    return (level, type_.hashCode())
