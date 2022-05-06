__all__ = [
    'dump_dataobject',
    'load_dataobject',
]

import dataclasses

import yaml

from g1.bases import dataclasses as g1_dataclasses


def load_dataobject(dataclass, path, **kwargs):
    return g1_dataclasses.fromdict(
        dataclass,
        yaml.safe_load(path.read_text(), **kwargs),
    )


def dump_dataobject(dataobject, path, **kwargs):
    path.write_text(yaml.safe_dump(dataclasses.asdict(dataobject), **kwargs))
