__all__ = [
    'BASE_IMAGE_RELEASE_CODE_NAME',
    # Pod.
    'PodConfig',
    'generate_machine_name',
    'generate_pod_id',
    'validate_pod_id',
    'validate_pod_name',
    'validate_pod_version',
    # XAR.
    'validate_xar_name',
    # App.
    'validate_app_name',
    # Image.
    'validate_image_id',
    'validate_image_name',
    'validate_image_tag',
    'validate_image_version',
    # Host system.
    'machine_id_to_pod_id',
    'pod_id_to_machine_id',
    'read_host_machine_id',
    'read_host_pod_id',
]

import dataclasses
import re
import typing
import uuid
from pathlib import Path

from g1.bases.assertions import ASSERT

BASE_IMAGE_RELEASE_CODE_NAME = 'focal'

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

# We do not support "process" and "none" for now.
_KILL_MODES = frozenset((
    'control-group',
    'mixed',
    None,
))


@dataclasses.dataclass(frozen=True)
class PodConfig:

    @dataclasses.dataclass(frozen=True)
    class App:
        """Descriptor of systemd unit file of container app."""

        name: str
        exec: typing.List[str] = dataclasses.field(default_factory=list)
        type: typing.Optional[str] = None
        user: str = 'nobody'
        group: str = 'nogroup'
        kill_mode: typing.Optional[str] = None

        # Advanced usage for overriding the entire service section
        # generation.
        service_section: typing.Optional[str] = None

        # TODO: Support ".timer" and ".socket" unit file.

        def __post_init__(self):
            validate_app_name(self.name)
            if self.service_section is None:
                ASSERT.not_empty(self.exec)
                ASSERT.in_(self.type, _SERVICE_TYPES)
                ASSERT.in_(self.kill_mode, _KILL_MODES)
            else:
                ASSERT.empty(self.exec)
                ASSERT.none(self.type)
                ASSERT.none(self.kill_mode)

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
        """Configure a bind mount."""

        source: str
        target: str
        read_only: bool = True

        def __post_init__(self):
            # Empty source path means host's /var/tmp.
            if self.source:
                ASSERT.predicate(Path(self.source), Path.is_absolute)
            ASSERT.predicate(Path(self.target), Path.is_absolute)

    @dataclasses.dataclass(frozen=True)
    class Overlay:
        """Configure an overlay.

        This is more advanced and flexible than ``Mount`` above.
        """

        sources: typing.List[str]
        target: str
        read_only: bool = True

        def __post_init__(self):
            ASSERT.not_empty(self.sources)
            for i, source in enumerate(self.sources):
                # Empty source path means host's /var/tmp.
                if source:
                    ASSERT.predicate(Path(source), Path.is_absolute)
                else:
                    ASSERT.equal(i, len(self.sources) - 1)
            ASSERT.predicate(Path(self.target), Path.is_absolute)

    name: str
    version: str
    apps: typing.List[App]
    # Image are ordered from low to high.
    images: typing.List[Image]
    mounts: typing.List[Mount] = ()
    overlays: typing.List[Overlay] = ()

    def __post_init__(self):
        validate_pod_name(self.name)
        validate_pod_version(self.version)
        ASSERT.not_empty(self.images)
        ASSERT.unique(app.name for app in self.apps)
        ASSERT.unique(
            [mount.target for mount in self.mounts] + \
            [overlay.target for overlay in self.overlays]
        )


# Generic name and version pattern.
# For now, let's only allow a restrictive set of names.
_NAME_PATTERN = re.compile(r'[a-z0-9]+(-[a-z0-9]+)*')
_VERSION_PATTERN = re.compile(r'[a-z0-9]+((?:-|\.)[a-z0-9]+)*')


def validate_name(name):
    return ASSERT.predicate(name, _NAME_PATTERN.fullmatch)


def validate_version(version):
    return ASSERT.predicate(version, _VERSION_PATTERN.fullmatch)


# For now these are just an alias of the generic validator.
validate_pod_name = validate_name
validate_pod_version = validate_version
validate_app_name = validate_name
validate_image_name = validate_name
validate_image_version = validate_version
validate_image_tag = validate_name

_UUID_PATTERN = re.compile(
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
)


def validate_pod_id(pod_id):
    return ASSERT.predicate(pod_id, _UUID_PATTERN.fullmatch)


def generate_pod_id():
    return validate_pod_id(str(uuid.uuid4()))


def generate_machine_name(pod_id):
    return 'pod-%s' % pod_id


# Allow xar names like "foo_bar.sh".
_XAR_NAME_PATTERN = re.compile(r'[\w\-.]+')


def validate_xar_name(name):
    return ASSERT.predicate(name, _XAR_NAME_PATTERN.fullmatch)


# SHA-256.
_IMAGE_ID_PATTERN = re.compile(r'[0-9a-f]{64}')


def validate_image_id(image_id):
    return ASSERT.predicate(image_id, _IMAGE_ID_PATTERN.fullmatch)


def machine_id_to_pod_id(machine_id):
    ASSERT.equal(len(machine_id), 32)
    return '%s-%s-%s-%s-%s' % (
        machine_id[0:8],
        machine_id[8:12],
        machine_id[12:16],
        machine_id[16:20],
        machine_id[20:32],
    )


def pod_id_to_machine_id(pod_id):
    return pod_id.replace('-', '')


def read_host_machine_id():
    return Path('/etc/machine-id').read_text().strip()


def read_host_pod_id():
    return machine_id_to_pod_id(read_host_machine_id())
