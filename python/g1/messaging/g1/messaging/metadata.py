"""Manipulate metadata stored in a class object."""

__all__ = [
    'get_metadata',
    'set_metadata',
]

# Where metadata is stored in a class object.
_METADATA = '__g1_messaging_metadata__'


def get_metadata(cls, key, default=None):
    return getattr(cls, _METADATA, {}).get(key, default)


def set_metadata(cls, key, md):
    try:
        md_dict = getattr(cls, _METADATA)
    except AttributeError:
        md_dict = {}
        setattr(cls, _METADATA, md_dict)
    md_dict[key] = md
