"""Build rule template for and object model of images and pods."""

__all__ = [
    # Object model
    'App',
    'Image',
    'Pod',
    'SystemdUnit',
    'Volume',
    # Build rule template as decorator
    'app_specifier',
    'image_specifier',
    'pod_specifier',
]

from collections import OrderedDict, namedtuple
import functools
import hashlib
import json
import logging
import re

from garage import scripts

from foreman import define_parameter, define_rule, rule, to_path

from . import utils


LOG = logging.getLogger(__name__)


### Build rule template


#
# We want the best of both worlds for application pod metadata:
#
# * Rules may declare dependencies, which is the only way to instruct
#   foreman to load more build files, but rules are only executed at
#   build time.
#
# * Parameters may not declare dependencies (not technically impossible,
#   but this feature is somehow not implemented), but parameters can be
#   evaluated anytime.
#
# These application pod metadata are parameters, which means we may
# evaluate them anytime (this makes scripting easier because scripts
# that parse metadata do not have to execute builds beforehand).
#
# In addition, we provide do-nothing "specify" rules for the purpose of
# declaring parameter dependencies; if a parameter is defined in another
# build file, you simply declare a dependency between the specify rules,
# and foreman will load that build file.
#
# There is one more advantage of do-nothing specify rules: It makes
# build_pod rules do not directly depend on build_image rules; and so
# you (or build scripts) may build pods and images separately.
#


def specifier_decorator(decorator):
    def wrapper(specifier_or_object_name):
        if isinstance(specifier_or_object_name, str):
            return functools.partial(
                decorator,
                object_name=specifier_or_object_name,
            )
        else:
            return decorator(specifier_or_object_name)
    return wrapper


def with_object_name(specifier, object_name):
    """Wrap a specifier and insert a default object name."""
    if not object_name:
        # AC name does not accept underscore character
        object_name = specifier.__name__.replace('_', '-')
    def wrapper(parameters):
        obj = specifier(parameters)
        if obj._name is None:
            obj._name = object_name
        return obj
    return wrapper


AppRules = namedtuple('AppRules', 'specify_app')


@specifier_decorator
def app_specifier(specifier, object_name=None):
    """Define NAME/specify_app rule."""

    name = specifier.__name__ + '/'

    (App.define_parameter(specifier.__name__)
     .with_derive(with_object_name(specifier, object_name)))

    specify_app = (
        define_rule(name + 'specify_app')
        .depend('//base:build')
    )

    return AppRules(specify_app=specify_app)


ImageRules = namedtuple(
    'ImageRules', 'specify_image write_manifest build_image')


@specifier_decorator
def image_specifier(specifier, object_name=None):
    """Define these rules:
       * NAME/specify_image
       * NAME/write_manifest
       * NAME/build_image

       The output will be written to OUTPUT/IMAGE_NAME directory.
    """

    # TODO: Encrypt and/or sign the image

    name = specifier.__name__ + '/'

    (Image.define_parameter(specifier.__name__)
     .with_derive(with_object_name(specifier, object_name)))

    specify_image = (
        define_rule(name + 'specify_image')
        .depend('//base:build')
        .with_annotation('rule-type', 'specify_image')  # For do-build tool
        .with_annotation('build-image-rule', name + 'build_image')
    )

    @rule(name + 'write_manifest')
    @rule.depend('//base:tapeout')
    @rule.depend(name + 'specify_image')
    def write_manifest(parameters):
        """Create Appc image manifest file."""
        LOG.info('write appc image manifest: %s', name)
        image = parameters[specifier.__name__]
        utils.write_json_to(
            image.image_manifest,
            parameters['//base:drydock/manifest'],
        )

    @rule(name + 'build_image')
    @rule.depend(name + 'write_manifest')
    @rule.annotate('rule-type', 'build_image')  # For do-build tool
    @rule.annotate('image-parameter', specifier.__name__)
    def build_image(parameters):
        """Build Appc container image."""

        image = parameters[specifier.__name__]

        output_dir = parameters['//base:output'] / image.name
        LOG.info('build appc image: %s', output_dir)

        image_data_dir = parameters['//base:drydock/build']
        scripts.ensure_file(image_data_dir / 'manifest')
        scripts.ensure_directory(image_data_dir / 'rootfs')

        scripts.mkdir(output_dir)
        image_path = output_dir / 'image.aci'
        if image_path.exists():
            LOG.warning('overwrite: %s', image_path)
        image_checksum_path = output_dir / 'sha512'

        scripts.pipeline(
            [
                lambda: scripts.tar_create(
                    image_data_dir, ['manifest', 'rootfs'],
                    tarball_path=None,
                    tar_extra_flags=['--numeric-owner'],
                ),
                lambda: _compute_sha512(image_checksum_path),
                lambda: scripts.gzip(speed=9),
            ],
            # Don't close file opened from image_path here because
            # pipeline() will close it
            pipe_output=image_path.open('wb'),
        )
        scripts.ensure_file(image_path)
        scripts.ensure_file(image_checksum_path)

    return ImageRules(
        specify_image=specify_image,
        write_manifest=write_manifest,
        build_image=build_image,
    )


def _compute_sha512(sha512_file_path):
    hasher = hashlib.sha512()
    pipe_input = scripts.get_stdin()
    pipe_output = scripts.get_stdout()
    while True:
        data = pipe_input.read(4096)
        if not data:
            break
        hasher.update(data)
        pipe_output.write(data)
    sha512_file_path.write_text('%s\n' % hasher.hexdigest())


PodRules = namedtuple('PodRules', 'specify_pod build_pod')


@specifier_decorator
def pod_specifier(specifier, object_name=None):
    """Define NAME/build_pod rule.

       The output will be written to OUTPUT directory (note that images
       are written to OUTPUT/IMAGE_NAME).
    """

    name = specifier.__name__ + '/'

    (Pod.define_parameter(specifier.__name__)
     .with_derive(with_object_name(specifier, object_name)))

    define_parameter(name + 'version')

    specify_pod = (
        define_rule(name + 'specify_pod')
        .depend('//base:build')
        .with_annotation('rule-type', 'specify_pod')  # For do-build tool
    )

    @rule(name + 'build_pod')
    @rule.depend(name + 'specify_pod')
    @rule.annotate('rule-type', 'build_pod')  # For do-build tool
    @rule.annotate('pod-parameter', specifier.__name__)
    @rule.annotate('version-parameter', name + 'version')
    def build_pod(parameters):
        """Write out pod-related data files."""

        pod = parameters[specifier.__name__]
        pod._version = parameters[name + 'version']
        for image in pod.images:
            image.load_id(parameters)

        # Construct the pod object and write it out to disk
        utils.write_json_to(
            pod.pod_object,
            parameters['//base:output'] / 'pod.json',
        )

        # Copy systemd unit files; it has to matches the "unit-file"
        # entry of unit.pod_object_entry
        if pod.systemd_units:
            scripts.rsync(
                [unit.path for unit in pod.systemd_units],
                parameters['//base:output'],
            )

    return PodRules(specify_pod=specify_pod, build_pod=build_pod)


### Object model


# https://github.com/appc/spec/blob/master/spec/types.md
AC_IDENTIFIER_PATTERN = re.compile(r'[a-z0-9]+([-._~/][a-z0-9]+)*')
AC_NAME_PATTERN = re.compile(r'[a-z0-9]+(-[a-z0-9]+)*')


# Convention:
# pod_object_entry generates sub-entry of the pod object
# pod_manifest_entry_* generates sub-entry of the Appc pod manifest


class ModelObject:

    # TODO: Use the new annotation syntax after we upgrade to Python 3.6
    FIELDS = []

    @classmethod
    def define_parameter(cls, name):
        return (define_parameter(name)
                .with_type(cls)
                .with_parse(cls.from_dict)
                .with_encode(cls.to_dict))

    @classmethod
    def from_dict(cls, data):
        if isinstance(data, str):
            data = json.loads(data)
        else:
            data = dict(data)  # Make a copy before modifying
        for name, annotation in cls.FIELDS:
            if name not in data:
                pass
            elif isinstance(annotation, list) and len(annotation) == 1:
                element_type = annotation[0]
                data[name] = list(map(element_type.from_dict, data[name]))
            elif (isinstance(annotation, type) and
                  issubclass(annotation, ModelObject)):
                data[name] = annotation.from_dict(data[name])
        return cls(**data)

    @classmethod
    def to_dict(cls, obj):
        data = OrderedDict()
        for name, annotation in cls.FIELDS:
            if annotation is None:
                data[name] = getattr(obj, name)
            elif (isinstance(annotation, type) and
                  issubclass(annotation, ModelObject)):
                data[name] = annotation.to_dict(getattr(obj, name))
            elif isinstance(annotation, list) and len(annotation) == 1:
                element_type = annotation[0]
                elements = getattr(obj, name)
                data[name] = list(map(element_type.to_dict, elements))
            else:
                raise AssertionError
        return data

    @staticmethod
    def _ensure_ac_identifier(name):
        if name is not None and not AC_IDENTIFIER_PATTERN.fullmatch(name):
            raise ValueError('not valid AC identifier: %s' % name)
        return name

    @staticmethod
    def _ensure_ac_name(name):
        if name is not None and not AC_NAME_PATTERN.fullmatch(name):
            raise ValueError('not valid AC name: %s' % name)
        return name


class Environment(ModelObject):

    @staticmethod
    def from_dict(data):
        return data

    @staticmethod
    def to_dict(obj):
        return OrderedDict(sorted(obj.items()))


class Volume(ModelObject):

    # TODO: Accept URI as well as path
    # TODO: Accept checksum, or calculate it from path

    FIELDS = [
        ('name', None),
        ('path', None),
        ('user', None),
        ('group', None),
        ('data', None),
        ('read_only', None),
    ]

    def __init__(self, *,
                 name,
                 path,
                 user='nobody', group='nogroup',
                 data=None,
                 read_only=True):
        self.name = self._ensure_ac_name(name)
        self.path = path
        self.user = user
        self.group = group
        self.data = data
        self.read_only = read_only

    @property
    def pod_object_entry(self):
        entry = {
            'name': self.name,
            'user': self.user,
            'group': self.group,
        }
        if self.data:
            entry['data'] = self.data
        return entry

    @property
    def pod_manifest_entry_volume(self):
        return {
            # 'source' will be inserted by ops tool
            'name': self.name,
            'kind': 'host',
            'readOnly': self.read_only,
            'recursive': True,
        }

    @property
    def pod_manifest_entry_mount_point(self):
        return {
            'name': self.name,
            'path': self.path,
            'readOnly': self.read_only,
        }


class App(ModelObject):

    FIELDS = [
        ('name', None),
        ('exec', None),
        ('user', None),
        ('group', None),
        ('working_directory', None),
        ('environment', Environment),
        ('volumes', [Volume]),
    ]

    def __init__(self, *,
                 name=None,
                 exec=None,
                 user='nobody', group='nogroup',
                 working_directory='/',
                 environment=None,
                 volumes=()):
        self._name = self._ensure_ac_name(name)
        self.exec = exec or []
        self.user = user
        self.group = group
        self.working_directory = working_directory
        self.environment = environment or {}
        self.volumes = volumes or []

    @property
    def name(self):
        assert self._name is not None
        return self._name

    @name.setter
    def name(self, new_name):
        self._name = self._ensure_ac_name(new_name)

    @property
    def pod_manifest_entry(self):
        return {
            'exec': self.exec,
            'user': self.user,
            'group': self.group,
            'workingDirectory': self.working_directory,
            'environment': [
                {'name': name, 'value': self.environment[name]}
                for name in sorted(self.environment)
            ],
            'mountPoints': [
                volume.pod_manifest_entry_mount_point
                for volume in self.volumes
            ],
        }


class Image(ModelObject):

    # TODO: Accept docker://... URI

    FIELDS = [
        ('id', None),
        ('name', None),
        ('app', App),
        ('read_only_rootfs', None),
    ]

    def __init__(self, *,
                 id=None,
                 name=None,
                 app,
                 read_only_rootfs=True):
        self._id = id
        self._name = self._ensure_ac_identifier(name)
        self.app = app
        self.read_only_rootfs = read_only_rootfs

    def load_id(self, parameters):
        if self._id is None:
            path = parameters['//base:output'] / self.name / 'sha512'
            self._id = 'sha512-%s' % path.read_text().strip()

    @property
    def id(self):
        if self._id is None:
            LOG.warning('image has no id: %s', self.name)
        return self._id

    @property
    def name(self):
        assert self._name is not None
        return self._name

    @name.setter
    def name(self, new_name):
        self._name = self._ensure_ac_identifier(new_name)

    @property
    def pod_object_entry(self):
        # image.aci is under OUTPUT/IMAGE_NAME
        # TODO: Generate "signature" field
        return {
            'id': self.id,
            'image': '%s/image.aci' % self.name,
        }

    @property
    def pod_manifest_entry(self):
        """Return an app entry embedded in pod manifest."""
        entry = {
            'name': self.app.name,
            'image': {
                'name': self.name,
                'id': self.id,
            },
            'app': self.app.pod_manifest_entry,
            'readOnlyRootFS': self.read_only_rootfs,
        }
        return entry

    @property
    def image_manifest(self):
        """Return Appc image manifest."""
        return {
            'acKind': 'ImageManifest',
            'acVersion': '0.8.10',
            'name': self.name,
            'labels': [
                {
                    'name': 'arch',
                    'value': 'amd64',
                },
                {
                    'name': 'os',
                    'value': 'linux',
                },
            ],
            'app': self.app.pod_manifest_entry,
        }


class SystemdUnit(ModelObject):

    # TODO: Accept URI for unit_file
    # TODO: Accept checksum, or calculate it from unit_file

    FIELDS = [
        ('unit_file', None),
        ('instances', None),
    ]

    def __init__(self, *, unit_file, instances=None):
        self.unit_file = unit_file
        self.instances = instances

    @property
    def path(self):
        return to_path(self.unit_file)

    @property
    def pod_object_entry(self):
        # "unit-file" is relative path to OUTPUT; use path.name matches
        # the rsync() call above
        entry = {'unit-file': self.path.name}
        if self.instances:
            entry['instances'] = self.instances
        return entry


class Pod(ModelObject):

    FIELDS = [
        ('name', None),
        ('version', None),
        ('images', [Image]),
        ('systemd_units', [SystemdUnit]),
    ]

    def __init__(self, *,
                 name=None,
                 version=None,
                 images=None,
                 systemd_units=None):
        self._name = self._ensure_ac_name(name)
        self._version = version
        self.images = images or []
        self.systemd_units = systemd_units or []
        self._volumes = None

    @property
    def name(self):
        assert self._name is not None
        return self._name

    @name.setter
    def name(self, new_name):
        self._name = self._ensure_ac_name(new_name)

    @property
    def version(self):
        if self._version is None:
            LOG.warning('pod has no version: %s', self.name)
        return self._version

    @property
    def volumes(self):
        # Collect distinct volumes
        if self._volumes is None:
            volumes = {
                volume.name: volume
                for image in self.images
                for volume in image.app.volumes
            }
            self._volumes = sorted(volumes.values(), key=lambda v: v.name)
        return self._volumes

    @property
    def pod_object(self):
        """Construct the pod object for the ops tool."""
        return {
            'name': self.name,
            'version': self.version,
            'manifest': self.pod_manifest,
            'systemd-units': [
                unit.pod_object_entry
                for unit in self.systemd_units
            ],
            'images': [
                image.pod_object_entry
                for image in self.images
            ],
            'volumes': [
                volume.pod_object_entry
                for volume in self.volumes
            ],
        }

    @property
    def pod_manifest(self):
        return {
            'acVersion': '0.8.10',
            'acKind': 'PodManifest',
            'apps': [
                image.pod_manifest_entry
                for image in self.images
            ],
            'volumes': [
                volume.pod_manifest_entry_volume
                for volume in self.volumes
            ],
        }
