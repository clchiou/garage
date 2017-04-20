"""YAML helpers."""

__all__ = [
    'represent_datetime',
    'represent_enum',
    'represent_mapping',
]

import collections
import datetime
import enum

import yaml

from garage import asserts


def represent_datetime(dumper, value, datetime_format=None):
    asserts.type_of(value, datetime.datetime)
    # NOTE: PyYaml implementation uses a regex for ISO-8601 string which
    # matches a ':' in timezone string :(
    if datetime_format is None:
        str_value = value.isoformat()
    else:
        str_value = value.strftime(datetime_format)
    return dumper.represent_scalar('tag:yaml.org,2002:timestamp', str_value)


def represent_enum(dumper, value):
    asserts.type_of(value, enum.Enum)
    value = value.value
    if isinstance(value, int):
        tag = 'tag:yaml.org,2002:int'
        value = str(value)
    elif isinstance(value, str):
        tag = 'tag:yaml.org,2002:str'
    else:
        raise ValueError(
            'cannot represent enum value %r of type %s' % (value, type(value)))
    return dumper.represent_scalar(tag, value)


def represent_mapping(dumper, value, flow_style=None):
    """Derived from BaseRepresenter.represent_mapping."""
    asserts.type_of(value, collections.Mapping)
    pairs = []
    tag = 'tag:yaml.org,2002:map'
    node = yaml.MappingNode(tag, pairs, flow_style=flow_style)
    if dumper.alias_key is not None:
        dumper.represented_objects[dumper.alias_key] = node
    best_style = True
    for item_key, item_value in value.items():
        node_key = dumper.represent_data(item_key)
        node_value = dumper.represent_data(item_value)
        if not isinstance(node_key, yaml.ScalarNode) or node_key.style:
            best_style = False
        if not isinstance(node_value, yaml.ScalarNode) or node_value.style:
            best_style = False
        pairs.append((node_key, node_value))
    if flow_style is None:
        if dumper.default_flow_style is not None:
            node.flow_style = dumper.default_flow_style
        else:
            node.flow_style = best_style
    return node
