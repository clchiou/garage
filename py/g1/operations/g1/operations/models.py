__all__ = [
    'PodDeployInstruction',
    'XarDeployInstruction',
]

import dataclasses
import typing

from g1.containers import models as ctr_models


@dataclasses.dataclass(frozen=True)
class PodDeployInstruction:

    @dataclasses.dataclass(frozen=True)
    class Volume:
        label: str
        version: str
        target: str
        read_only: bool = True

    pod_config_template: ctr_models.PodConfig
    volumes: typing.List[Volume]


@dataclasses.dataclass(frozen=True)
class XarDeployInstruction:
    name: str
    version: str
    exec_relpath: str
    image: ctr_models.PodConfig.Image
