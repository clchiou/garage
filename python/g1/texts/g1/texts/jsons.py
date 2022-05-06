__all__ = [
    'dump_dataobject',
    'load_dataobject',
]

import dataclasses
import json

from g1.bases import dataclasses as g1_dataclasses


def load_dataobject(dataclass, path, **kwargs):
    return g1_dataclasses.fromdict(
        dataclass,
        json.loads(path.read_bytes(), **kwargs),
    )


def dump_dataobject(dataobject, path, **kwargs):
    path.write_text(
        json.dumps(dataclasses.asdict(dataobject), **kwargs),
        encoding='ascii',
    )
