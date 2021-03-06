__all__ = [

    'ReleaseRepo',

    'PodInstruction',
    'SimpleInstruction',
    'execute_instructions',

    'get_git_stamp',
    'get_hg_stamp',
]

from pathlib import Path
import datetime
import logging
import tempfile
import yaml

from foreman import Label

from garage import scripts
from garage.assertions import ASSERT

import shipyard


LOG = logging.getLogger(__name__)


class ReleaseRepo:

    @staticmethod
    def get_instruction_path(root, kind, label, version):
        # Don's use with_suffix('.yaml') because version may contain
        # dots, e.g., "1.0.3".
        return root / kind / label.path / label.name / (version + '.yaml')

    @staticmethod
    def detect_instruction_path(root, label, version):
        paths = {}
        for kind in ('pods', 'volumes'):
            path = ReleaseRepo.get_instruction_path(root, kind, label, version)
            if path.exists():
                paths[kind] = path
        if not paths:
            raise FileNotFoundError(
                'expect instructions under: %s %s %s' % (root, label, version))
        if len(paths) > 1:
            raise RuntimeError(
                'expect unique instruction: %s' % sorted(paths.values()))
        return paths.popitem()

    def __init__(self, release_root, rules):
        self.root = scripts.ensure_path(release_root)
        self.rules = rules

    def load_instructions(self, labels_versions):

        data_list = []
        rule_list = []
        for label, version in labels_versions:
            LOG.info('load release %s@%s', label, version)
            _, path = self.detect_instruction_path(self.root, label, version)
            data = yaml.load(path.read_text())
            rule = data.get('rule')
            if not rule:
                raise ValueError('instruction does not specify rule')
            rule_list.append(Label.parse(rule, implicit_path=label.path))
            data_list.append(data)

        self.rules.load_from_labels(rule_list)

        return [
            self._make_instruction(data_list[i], rule_list[i], label, version)
            for i, (label, version) in enumerate(labels_versions)
        ]

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

        return [self._make_instruction(*blob) for blob in blobs]

    def _make_instruction(self, data, rule, pod, version):

        # Check if instruction file overwrites pod and version.
        pod = data.get('pod', pod)
        version = data.get('version', version)

        parameters = [
            (Label.parse(label, implicit_path=rule.path), value)
            for label, value in sorted(data.get('parameters', {}).items())
        ]
        parameters.sort()

        rule_type = self.rules.get_rule(rule).annotations.get('rule-type')
        if rule_type == 'build_pod':
            return self._make_pod_instruction(
                data,
                rule, pod, version,
                parameters,
            )
        elif rule_type == 'build_volume':
            return SimpleInstruction(
                kind='volumes',
                rule=rule, target=pod, version=version,
                parameters=parameters,
            )
        else:
            # FIXME: This is probably confusing: Although this is not a
            # pod, we still put it to `pods` directory.  We do this just
            # because it is convenient, not because it is right.
            return SimpleInstruction(
                kind='pods',
                rule=rule, target=pod, version=version,
                parameters=parameters,
            )

    def _make_pod_instruction(self, data, rule, pod, version, parameters):

        self._check_pod(rule, pod)

        pod_parameter = self._get_pod_parameter(rule)

        build_image_rules = shipyard.get_build_image_rules(
            self.rules,
            self.rules.get_rule(rule),
        )

        build_volume_rules = shipyard.get_build_volume_rules(
            self.rules,
            self.rules.get_rule(rule),
        )

        parse_label = lambda l: Label.parse(l, implicit_path=rule.path)

        instruction = PodInstruction(
            rule=rule,
            pod=pod,
            version=version,
            images={
                parse_label(label): version
                for label, version in data.get('images', {}).items()
            },
            image_rules={},  # Set it in _add_default_images().
            volumes={
                parse_label(label): version
                for label, version in data.get('volumes', {}).items()
            },
            volume_mapping={
                parse_label(l1): parse_label(l2)
                for l1, l2 in pod_parameter.default['volume_mapping']
            },
            volume_rules={},  # Set in _add_volume_rules().
            parameters=parameters,
        )

        self._add_default_images(instruction, build_image_rules)
        self._add_default_volumes(instruction, build_image_rules)

        self._add_volume_rules(instruction, build_volume_rules)

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
                raise ValueError('invalid relative path: %s' % relpath)
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

    def _get_pod_parameter(self, rule):
        pod = self.rules.get_rule(rule)
        pod = self.rules.get_parameter(
            pod.annotations['pod-parameter'],
            implicit_path=pod.label.path,
        )
        return pod

    def _check_pod(self, rule, pod):
        pod2 = self.rules.get_pod_name(self.rules.get_rule(rule))
        if pod2 != pod:
            fmt = 'pod from build file differs from instruction: %s != %s'
            raise ValueError(fmt % (pod2, pod))

    def _add_default_images(self, instruction, build_image_rules):
        for rule in build_image_rules:
            image = self.rules.get_parameter(
                rule.annotations['image-parameter'],
                implicit_path=rule.label.path,
            )
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
            app = self.rules.get_parameter(
                specify_app_rule.annotations['app-parameter'],
                implicit_path=specify_app_rule.label.path,
            )
            # Include only volumes that provide `data` path.
            for volume in app.default['volumes']:
                if not volume.get('data'):
                    continue
                instruction.volumes.setdefault(
                    Label.parse_name(app.label.path, volume['name']),
                    instruction.version,
                )

    def _add_volume_rules(self, instruction, build_volume_rules):
        for rule in build_volume_rules:
            volume = self.rules.get_parameter(
                rule.annotations['volume-parameter'],
                implicit_path=rule.label.path,
            )
            volume = Label.parse_name(rule.label.path, volume.default['name'])
            instruction.volume_rules[volume] = rule.label


def execute_instructions(instructions, repo, builder, input_roots):
    for instruction in instructions:
        LOG.info('execute release instruction: %s', instruction)
        if not instruction.execute(repo, builder, input_roots):
            return False  # Fail early.
    return True


class PodInstruction:
    """Release instruction of pods.

    It tracks extra info for building images, etc.
    """

    def __init__(self, **kwargs):
        # Pod build rule.
        self.rule = ASSERT.type_of(kwargs.pop('rule'), Label)
        # Label that refers to the pod (not pod build rule).
        self.pod = ASSERT.type_of(kwargs.pop('pod'), Label)
        # Pod version.
        self.version = kwargs.pop('version')
        # Map image label to version.
        self.images = kwargs.pop('images')
        # Buile rules of the images.
        self.image_rules = kwargs.pop('image_rules')
        # Map volume label to version.
        self.volumes = kwargs.pop('volumes')
        self.volume_mapping = kwargs.pop('volume_mapping')
        self.volume_rules = kwargs.pop('volume_rules')
        self.parameters = kwargs.pop('parameters')
        if kwargs:
            raise ValueError('unknown names: %s' % ', '.join(sorted(kwargs)))

    def __str__(self):
        return '%s@%s' % (self.pod, self.version)

    def execute(self, repo, builder, input_roots):

        build_name = 'build-%d' % datetime.datetime.now().timestamp()

        # Skip building pod if it is present.
        if self._get_pod_path(repo).exists():
            LOG.info('skip building pod: %s@%s', self.pod, self.version)
            return True

        # Build images that are not present.
        for image in sorted(self.images):
            self._build_image(repo, builder, build_name, image, input_roots)

        # Build volumes that are not present.
        for volume in sorted(self.volumes):
            self._build_volume(repo, builder, build_name, volume, input_roots)

        # Finally we build the pod.
        self._build_pod(repo, builder, build_name)

        return True

    def _get_mapped_to_volume_label(self, volume):
        while volume in self.volume_mapping:
            volume = self.volume_mapping[volume]
        return volume

    def _get_pod_path(self, repo):
        return (repo.root / 'pods' /
                self.pod.path / self.pod.name / self.version)

    def _get_image_path(self, repo, image):
        return (repo.root / 'images' /
                image.path / image.name / self.images[image])

    def _get_volume_path(self, repo, volume):
        version = self.volumes[volume]
        volume = self._get_mapped_to_volume_label(volume)
        return repo.root / 'volumes' / volume.path / volume.name / version

    def _build_image(self, repo, builder, build_name, image, input_roots):
        image_lv = '%s@%s' % (image, self.images[image])
        image_path = self._get_image_path(repo, image)
        if image_path.exists():
            LOG.info('skip building existed image: %s', image_lv)
            return

        image_uri = self._get_image_uri(repo, self.image_rules[image])
        if image_uri:
            LOG.info(
                'skip building image because it is from registry: %s %s',
                image_lv, image_uri,
            )
            return

        LOG.info('build image %s -> %s', self.image_rules[image], image_lv)

        version_label = self._get_version_label(repo, self.image_rules[image])

        with tempfile.TemporaryDirectory() as build_dir:

            args = [
                '--build-name', build_name,
                '--parameter', '%s=%s' % (version_label, self.version),
                '--output', build_dir,
            ]

            input_root, input_path = shipyard.find_input_path(
                input_roots, 'image-data', image)
            if input_root is not None:
                LOG.info('use image data: %s %s', input_root, input_path)
                args.extend(['--input', input_root, input_path])

            add_parameters(args, self.parameters)

            builder.build(self.image_rules[image], extra_args=args)
            scripts.mkdir(image_path.parent)
            scripts.cp(
                Path(build_dir) / image.name, image_path,
                recursive=True,
            )

    def _build_volume(self, repo, builder, build_name, original, input_roots):
        volume = self._get_mapped_to_volume_label(original)
        volume_lv = '%s@%s' % (volume, self.volumes[original])
        volume_path = self._get_volume_path(repo, original)
        if volume_path.exists():
            LOG.info('skip building volume: %s', volume_lv)
            return

        LOG.info('build volume %s -> %s', self.volume_rules[volume], volume_lv)

        version_label = self._get_version_label(
            repo, self.volume_rules[volume])

        tarball_filename = self._get_volume_tarball_filename(
            repo, self.volume_rules[volume])

        with tempfile.TemporaryDirectory() as build_dir:

            args = [
                '--build-name', build_name,
                '--parameter', '%s=%s' % (version_label, self.version),
                '--output', build_dir,
            ]

            input_root, input_path = shipyard.find_input_path(
                input_roots, 'volume-data', volume)
            if input_root is not None:
                LOG.info('use volume data: %s %s', input_root, input_path)
                args.extend(['--input', input_root, input_path])

            add_parameters(args, self.parameters)

            builder.build(self.volume_rules[volume], extra_args=args)
            scripts.mkdir(volume_path)
            scripts.cp(Path(build_dir) / tarball_filename, volume_path)

    def _build_pod(self, repo, builder, build_name):

        LOG.info('build pod %s -> %s', self.rule, self)

        version_label = self._get_version_label(repo, self.rule)

        images_from_registry = frozenset(
            image
            for image in self.images
            if self._get_image_uri(repo, self.image_rules[image])
        )

        with tempfile.TemporaryDirectory() as build_dir:

            # Builder is running in a container and so symlinks won't
            # work; to work around this, we copy files to build_dir (and
            # for now all we need to copy is `image-name/sha512`).
            for image in self.images:
                if image in images_from_registry:
                    continue
                image_path = self._get_image_path(repo, image)
                scripts.mkdir(build_dir / image.name)
                scripts.cp(image_path / 'sha512', build_dir / image.name)

            builder.build(self.rule, extra_args=add_parameters(
                [
                    '--build-name', build_name,
                    '--parameter', '%s=%s' % (version_label, self.version),
                    '--output', build_dir,
                ],
                self.parameters,
            ))

            # Undo the workaround.
            for image in self.images:
                if image in images_from_registry:
                    continue
                scripts.rm(build_dir / image.name, recursive=True)

            pod_path = self._get_pod_path(repo)
            scripts.mkdir(pod_path.parent)
            scripts.cp(build_dir, pod_path, recursive=True)

            # Create symlink to images.
            for image in self.images:
                if image in images_from_registry:
                    continue
                image_path = self._get_image_path(repo, image)
                link_path = pod_path / image.name
                if link_path.exists():
                    LOG.warning('refuse to overwrite: %s', link_path)
                    continue
                scripts.symlink_relative(image_path, link_path)

            # Create symlink to volumes.
            for volume in self.volumes:
                volume_path = self._get_volume_path(repo, volume)
                link_path = pod_path / volume.name
                if link_path.exists():
                    LOG.warning('refuse to overwrite: %s', link_path)
                    continue
                scripts.symlink_relative(volume_path, link_path)

    @staticmethod
    def _get_version_label(repo, rule):
        version_parameter = repo.rules.get_parameter(
            repo.rules.get_rule(rule).annotations['version-parameter'],
            implicit_path=rule.path,
        )
        return version_parameter.label

    @staticmethod
    def _get_image_uri(repo, image_rule_label):
        image_rule = repo.rules.get_rule(image_rule_label)
        image_parameter = repo.rules.get_parameter(
            image_rule.annotations['image-parameter'],
            implicit_path=image_rule.label.path,
        )
        return image_parameter.default['image_uri']

    @staticmethod
    def _get_volume_tarball_filename(repo, rule):
        volume_parameter = repo.rules.get_parameter(
            repo.rules.get_rule(rule).annotations['volume-parameter'],
            implicit_path=rule.path,
        )
        return volume_parameter.default['tarball_filename']


class SimpleInstruction:
    """Release instruction of a single build rule."""

    def __init__(self, *, kind, rule, target, version, parameters):
        self.kind = kind
        self.rule = rule
        self.target = target
        self.version = version
        self.parameters = parameters

    def __str__(self):
        return '%s@%s' % (self.target, self.version)

    def execute(self, repo, builder, input_roots):
        LOG.info('build %s -> %s', self.rule, self)
        build_name = 'build-%d' % datetime.datetime.now().timestamp()
        output_path = (
            repo.root / self.kind /
            self.target.path / self.target.name / self.version
        )

        args = [
            '--build-name', build_name,
            '--output', output_path,
        ]

        if self.kind == 'volumes':
            input_root, input_path = shipyard.find_input_path(
                input_roots, 'volume-data', self.target)
            if input_root is not None:
                LOG.info('use volume data: %s %s', input_root, input_path)
                args.extend(['--input', input_root, input_path])

        add_parameters(args, self.parameters)

        builder.build(self.rule, extra_args=args)

        return True


def get_git_stamp(path):

    with scripts.directory(path):

        cmd = ['git', 'remote', '--verbose']
        remotes = scripts.execute(cmd, capture_stdout=True).stdout
        for remote in remotes.decode('utf8').split('\n'):
            remote = remote.split()
            if remote[0] == 'origin':
                url = remote[1]
                break
        else:
            raise RuntimeError('no remote origin for %s' % path)

        cmd = ['git', 'log', '-1', '--format=format:%H']
        revision = scripts.execute(cmd, capture_stdout=True).stdout
        revision = revision.decode('ascii').strip()

        dirty = False
        cmd = ['git', 'status', '--porcelain']
        status = scripts.execute(cmd, capture_stdout=True).stdout
        for status_line in status.decode('utf8').split('\n'):
            # Be careful of empty line!
            if status_line and not status_line.startswith('  '):
                dirty = True
                break

    return url, revision, dirty


def get_hg_stamp(path):

    with scripts.directory(path):

        cmd = ['hg', 'path']
        remotes = scripts.execute(cmd, capture_stdout=True).stdout
        for remote in remotes.decode('utf8').split('\n'):
            remote = remote.split()
            if remote[0] == 'default':
                ASSERT.equal(remote[1], '=')
                url = remote[2]
                break
        else:
            raise RuntimeError('no default remote for %s' % path)

        cmd = ['hg', 'log', '--limit', '1', '--template', '{node}']
        revision = scripts.execute(cmd, capture_stdout=True).stdout
        revision = revision.decode('ascii').strip()

        cmd = ['hg', 'status']
        dirty = scripts.execute(cmd, capture_stdout=True).stdout
        dirty = bool(dirty.strip())

    return url, revision, dirty


def add_parameters(extra_args, parameters):
    for label, value in parameters:
        extra_args.append('--parameter')
        extra_args.append('%s=%s' % (label, value))
    return extra_args
