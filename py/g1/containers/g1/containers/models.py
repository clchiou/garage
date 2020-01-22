__all__ = [
    # Pod.
    'PodConfig',
    'generate_pod_id',
    'validate_pod_id',
    # Image.
    'validate_image_id',
    'validate_image_name',
    'validate_image_tag',
    'validate_image_version',
]

import dataclasses
import re
import typing
import uuid
from pathlib import Path

from g1.bases.assertions import ASSERT

_SERVICE_TYPES = frozenset((
    'simple',
    'exec',
    'forking',
    'oneshot',
    'dbus',
    'notify',
    'idle',
    None,
))


@dataclasses.dataclass(frozen=True)
class PodConfig:

    @dataclasses.dataclass(frozen=True)
    class App:
        """Descriptor of systemd unit file of container app."""

        name: str
        exec: typing.List[str]
        type: typing.Optional[str] = None
        user: str = 'nobody'
        group: str = 'nogroup'

        # TODO: Support ".timer" and ".socket" unit file.

        def __post_init__(self):
            validate_image_name(self.name)
            ASSERT.not_empty(self.exec)
            ASSERT.in_(self.type, _SERVICE_TYPES)

    @dataclasses.dataclass(frozen=True)
    class Image:

        id: typing.Optional[str] = None
        name: typing.Optional[str] = None
        version: typing.Optional[str] = None
        tag: typing.Optional[str] = None

        def __post_init__(self):
            ASSERT.only_one((self.id, self.name or self.version, self.tag))
            ASSERT.not_xor(self.name, self.version)
            if self.id:
                validate_image_id(self.id)
            elif self.name:
                validate_image_name(self.name)
                validate_image_version(self.version)
            else:
                validate_image_tag(self.tag)

    @dataclasses.dataclass(frozen=True)
    class Mount:

        source: str
        target: str
        read_only: bool = True

        def __post_init__(self):
            # Empty source path means host's /var/tmp.
            if self.source:
                ASSERT.predicate(Path(self.source), Path.is_absolute)
            ASSERT.predicate(Path(self.target), Path.is_absolute)

    name: str
    version: str
    apps: typing.List[App]
    # Image are ordered from low to high.
    images: typing.List[Image]
    mounts: typing.List[Mount] = ()

    def __post_init__(self):
        validate_image_name(self.name)
        validate_image_version(self.version)
        ASSERT.not_empty(self.images)
        ASSERT(
            len(set(u.name for u in self.apps)) == len(self.apps),
            'expect unique app names: {}',
            self.apps,
        )
        ASSERT(
            len(set(v.target for v in self.mounts)) == len(self.mounts),
            'expect unique mount targets: {}',
            self.mounts,
        )


_UUID_PATTERN = re.compile(
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
)


def validate_pod_id(pod_id):
    return ASSERT.predicate(pod_id, _UUID_PATTERN.fullmatch)


def generate_pod_id():
    return validate_pod_id(str(uuid.uuid4()))


# SHA-256.
_ID_PATTERN = re.compile(r'[0-9a-f]{64}')

# For now, let's only allow a restrictive set of names.
_NAME_PATTERN = re.compile(r'[a-z0-9]+(-[a-z0-9]+)*')
_VERSION_PATTERN = re.compile(r'[a-z0-9]+((?:-|\.)[a-z0-9]+)*')


def validate_image_id(image_id):
    return ASSERT.predicate(image_id, _ID_PATTERN.fullmatch)


def validate_image_name(name):
    return ASSERT.predicate(name, _NAME_PATTERN.fullmatch)


def validate_image_version(version):
    return ASSERT.predicate(version, _VERSION_PATTERN.fullmatch)


def validate_image_tag(tag):
    return ASSERT.predicate(tag, _NAME_PATTERN.fullmatch)
