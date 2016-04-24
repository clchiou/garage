__all__ = [
    'make_json_formatter',
    'make_yaml_formatter',
]

import datetime
import enum
from collections import Mapping
from collections import OrderedDict
from functools import partial


def make_json_formatter():
    import json
    from .json import encode_datetime
    from .json import encode_mapping
    from .json import join_encoders
    encoder = join_encoders(
        # Order by frequency (a very small optimization)
        encode_mapping,
        encode_datetime,
    )
    return partial(
        json.dumps,
        ensure_ascii=False,
        indent=4,
        default=encoder,
    )


def make_yaml_formatter():
    import yaml
    from .yaml import represent_datetime
    from .yaml import represent_enum
    from .yaml import represent_mapping
    yaml.SafeDumper.add_representer(datetime.datetime, represent_datetime)
    yaml.SafeDumper.add_multi_representer(enum.Enum, represent_enum)
    yaml.SafeDumper.add_multi_representer(Mapping, represent_mapping)
    # We need this because OrderedDict is not "strictly" a Mapping.
    yaml.SafeDumper.add_representer(OrderedDict, represent_mapping)
    return partial(
        yaml.safe_dump,
        default_flow_style=False,
        allow_unicode=True,
    )
