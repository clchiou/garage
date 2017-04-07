__all__ = [
    'ReleaseRepo',
    'Instruction',
    'execute_instructions',
]

from pathlib import Path
import datetime
import logging
import tempfile
import yaml

from foreman import Label

from garage import scripts

import shipyard


LOG = logging.getLogger(__name__)


class ReleaseRepo:

    def __init__(self, release_root, rules):
        self.root = scripts.ensure_path(release_root)
        self.rules = rules

    def load_instructions(self, labels_versions):

        data_list = []
        rule_list = []
        for label, version in labels_versions:
            LOG.info('load release %s@%s', label, version)
            # Don's use with_suffix('.yaml') because version may contain
            # dots, e.g., 1.0.3
            path = (self.root / 'pods' /
                    label.path / label.name / (version + '.yaml'))
            data = yaml.load(path.read_text())
            rule = data.get('rule')
            if not rule:
                raise ValueError('instruction does not specify rule')
            rule_list.append(Label.parse(rule, implicit_path=label.path))
            data_list.append(data)

        self.rules.load_from_labels(rule_list)

        instructions = []
        for i, (label, version) in enumerate(labels_versions):
            with self.rules.using_label_path(label):
                instructions.append(self._make_instruction(
                    data_list[i],
                    rule_list[i],
                    label,
                    version,
                ))
        return instructions

    def load_instruction_files(self, paths):

        blobs = []
        build_ids = set()
        for path in paths:
            LOG.info('load release instruction: %s', path)
            path = self._check_path(path)
            data = yaml.load(path.read_text())
            rule, pod, version = self._parse_rpv(path, data)
            blobs.append((data, rule, pod, version))
            # You should not build the same pod twice
            build_id = (pod, version)
            if build_id in build_ids:
                raise ValueError(
                    'duplicated instruction: %s@%s' % (pod, version))
            build_ids.add(build_id)

        self.rules.load_from_labels(rule for _, rule, _, _ in blobs)

        instructions = []
        for blob in blobs:
            with self.rules.using_label_path(blob[2]):
                instructions.append(self._make_instruction(*blob))
        return instructions

    def _make_instruction(self, data, rule, pod, version):

        self._check_pod(rule, pod)

        build_image_rules = shipyard.get_build_image_rules(
            self.rules,
            self.rules.get_rule(rule),
        )

        instruction = Instruction(
            rule=rule,
            pod=pod,
            version=version,
            images={
                Label.parse(label, implicit_path=rule.path): version
                for label, version in data.get('images', {}).items()
            },
            image_rules={},  # Set it in _add_default_images()
            volumes={
                Label.parse(label, implicit_path=rule.path): version
                for label, version in data.get('volumes', {}).items()
            },
        )

        self._add_default_images(instruction, build_image_rules)
        self._add_default_volumes(instruction, build_image_rules)

        return instruction

    def _check_path(self, path):
        path = scripts.ensure_path(path)
        if path.exists():
            if not path.is_absolute():
                path = path.resolve()
        else:
            # I guess it's a path relative to `pods` directory?
            path = scripts.ensure_file(self.root / 'pods' / path)
        if path.suffix != '.yaml':
            LOG.warning('expect file suffix to be .yaml: %s', path)
        return path

    def _parse_rpv(self, path, data):
        """Parse rule, pod, and version."""

        try:
            relpath = path.relative_to(self.root)
        except ValueError:
            inferred_pod = None
            inferred_version = None
        else:
            # relpath should be like:
            #   pods/LABEL_PATH/POD_NAME/VERSION.yaml
            LOG.debug('try to infer instruction data from %s', relpath)
            parts = relpath.parts
            if parts[0] != 'pods':
                raise ValueError('invalid relative path: %s', relpath)
            inferred_pod = '//%s:%s' % ('/'.join(parts[1:-2]), parts[-2])
            inferred_version = relpath.stem

        pod = data.get('pod', inferred_pod)
        if not pod:
            raise ValueError('instruction does not specify pod')
        if inferred_pod and inferred_pod != pod:
            LOG.warning('actual pod differs from the inferred: %s != %s',
                        pod, inferred_pod)
        pod = Label.parse(pod)

        version = data.get('version', inferred_version)
        if not version:
            raise ValueError('instruction does not specify version')
        if inferred_version is not None and inferred_version != version:
            LOG.warning('actual version differs from the inferred: %s != %s',
                        version, inferred_version)

        rule = data.get('rule')
        if not rule:
            raise ValueError('instruction does not specify rule')
        rule = Label.parse(rule, implicit_path=pod.path)

        return rule, pod, version

    def _check_pod(self, rule, pod):
        pod2 = self.rules.get_rule(rule)
        pod2 = pod2.annotations['pod-parameter']
        pod2 = self.rules.get_parameter(pod2)
        pod2 = Label.parse_name(rule.path, pod2.default['name'])
        if pod2 != pod:
            fmt = 'pod from build file differs from instruction: %s != %s'
            raise ValueError(fmt % (pod2, pod))

    def _add_default_images(self, instruction, build_image_rules):
        for rule in build_image_rules:
            image = rule.annotations['image-parameter']
            image = self.rules.get_parameter(image)
            image = Label.parse_name(rule.label.path, image.default['name'])
            instruction.images.setdefault(image, instruction.version)
            instruction.image_rules[image] = rule.label

    def _add_default_volumes(self, instruction, build_image_rules):
        for rule in build_image_rules:
            specify_app_rule = shipyard.get_specify_app_rule(
                self.rules,
                shipyard.get_specify_image_rule(
                    self.rules,
                    rule,
                ),
            )
            app = specify_app_rule.annotations['app-parameter']
            app = self.rules.get_parameter(app)
            for volume in app.default['volumes']:
                instruction.volumes.setdefault(
                    Label.parse_name(app.label.path, volume['name']),
                    instruction.version,
                )


def execute_instructions(instructions, repo, builder):
    for instruction in instructions:
        LOG.info('execute release instruction: %s', instruction)
        with repo.rules.using_label_path(instruction.rule):
            if not instruction.execute(repo, builder):
                return False  # Fail early
    return True


class Instruction:

    rule: Label
    pod: Label  # (rule label path, pod name)
    version: str
    images: dict  # Map (image label path, image name) to version
    image_rules: dict  # Map to build_image rules
    volumes: dict  # Map (app label path, volume name) to version

    def __init__(self, **kwargs):

        for name, type_ in self.__annotations__.items():
            if name not in kwargs:
                raise ValueError('missing field: %r' % name)
            value = kwargs[name]
            if not isinstance(value, type_):
                raise ValueError(
                    '%r is not %s-typed: %r' % (name, type_.__name__, value))

        unknown_names = set(kwargs).difference_update(self.__annotations__)
        if unknown_names:
            raise ValueError(
                'unknown names: %s' % ', '.join(sorted(unknown_names)))

        self.rule = kwargs['rule']
        self.pod = kwargs['pod']
        self.version = kwargs['version']
        self.images = kwargs['images']
        self.image_rules = kwargs['image_rules']
        self.volumes = kwargs['volumes']

    def __str__(self):
        return '%s@%s' % (self.pod, self.version)

    def execute(self, repo, builder):

        build_name = 'build-%d' % datetime.datetime.now().timestamp()

        # Build pod if it is not present
        if self._get_pod_path(repo).exists():
            LOG.info('skip building pod: %s@%s', self.pod, self.version)
            return True

        # Check if all volumes are present
        okay = True
        for volume in sorted(self.volumes):
            if not self._get_volume_path(repo, volume).exists():
                volume_lv = '%s@%s' % (volume, self.volumes[volume])
                LOG.error('volume does not exist: %s', volume_lv)
                okay = False
        if not okay:
            return False

        # Build images that are not present
        for image in sorted(self.images):
            self._build_image(repo, builder, build_name, image)

        # Finally we build the pod
        self._build_pod(repo, builder, build_name)

        return True

    def _get_pod_path(self, repo):
        return (repo.root / 'pods' /
                self.pod.path / self.pod.name / self.version)

    def _get_image_path(self, repo, image):
        return (repo.root / 'images' /
                image.path / image.name / self.images[image])

    def _get_volume_path(self, repo, volume):
        return (repo.root / 'volumes' /
                volume.path / volume.name / self.volumes[volume])

    def _build_image(self, repo, builder, build_name, image):
        image_lv = '%s@%s' % (image, self.images[image])
        image_path = self._get_image_path(repo, image)
        if image_path.exists():
            LOG.info('skip building image: %s', image_lv)
            return

        LOG.info('build image %s', image_lv)
        with tempfile.TemporaryDirectory() as build_dir:
            builder.build(self.image_rules[image], extra_args=[
                '--build-name', build_name,
                '--output', build_dir,
            ])
            scripts.mkdir(image_path.parent)
            scripts.cp(
                Path(build_dir) / image.name, image_path,
                recursive=True,
            )

    def _build_pod(self, repo, builder, build_name):
        LOG.info('build image %s@%s', self.pod, self.version)
        with tempfile.TemporaryDirectory() as build_dir:

            # Builder is running in a container and so symlinks won't
            # work; to work around this, we copy files to build_dir (and
            # for now all we need to copy is `image-name/sha512`)
            for image in self.images:
                image_path = self._get_image_path(repo, image)
                scripts.mkdir(build_dir / image.name)
                scripts.cp(image_path / 'sha512', build_dir / image.name)

            builder.build(self.rule, extra_args=[
                '--build-name', build_name,
                '--output', build_dir,
            ])

            # Undo the workaround
            for image in self.images:
                scripts.rm(build_dir / image.name, recursive=True)

            pod_path = self._get_pod_path(repo)
            scripts.mkdir(pod_path.parent)
            scripts.cp(build_dir, pod_path, recursive=True)

            # Create symlink to images
            for image in self.images:
                image_path = self._get_image_path(repo, image)
                scripts.symlink_relative(image_path, pod_path / image.name)

            # Create symlink to volumes
            for volume in self.volumes:
                volume_path = self._get_volume_path(repo, volume)
                scripts.symlink_relative(volume_path, pod_path / volume.name)
