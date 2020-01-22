__all__ = [
    'PodDeployInstruction',
    'XarDeployInstruction',
]

import dataclasses
import typing

from g1.bases.assertions import ASSERT
from g1.containers import models as ctr_models

# Bundle directory structure.
BUNDLE_DEPLOY_INSTRUCTION_FILENAME = 'deploy.json'
XAR_BUNDLE_IMAGE_FILENAME = 'image.tar.gz'
XAR_BUNDLE_ZIPAPP_FILENAME = 'app.zip'


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
    exec_relpath: typing.Optional[str]
    image: typing.Optional[ctr_models.PodConfig.Image]

    def __post_init__(self):
        ASSERT.not_xor(self.exec_relpath is None, self.image is None)

    def is_zipapp(self):
        return self.exec_relpath is None
