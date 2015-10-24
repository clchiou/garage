"""YAML helpers."""

__all__ = [
    'represent_datetime',
    'represent_mapping',
]

import collections
import datetime

import yaml


def represent_datetime(dumper, value, datetime_format=None):
    assert isinstance(value, datetime.datetime)
    if datetime_format is None:
        str_value = value.isoformat()
    else:
        str_value = value.strftime(datetime_format)
    return dumper.represent_scalar('tag:yaml.org,2002:timestamp', str_value)


def represent_mapping(dumper, value, flow_style=None):
    """Derived from BaseRepresenter.represent_mapping."""
    assert isinstance(value, collections.Mapping)
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
