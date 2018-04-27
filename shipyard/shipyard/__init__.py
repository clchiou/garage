"""\
Helpers for build scripts under `scripts` directory (these are not build
rule templates for helping you write build rules).
"""

__all__ = [
    'Builder',
    'RuleIndex',
    'find_default_path',
    'find_input_path',
    'get_build_image_rules',
    'get_specify_app_rule',
    'get_specify_image_rule',
    'get_specify_pod_rule',
    'with_builder_argument',
    'with_foreman_argument',
]

from collections import namedtuple
from pathlib import Path
import json

from foreman import Label

from garage import apps
from garage import scripts
from garage.assertions import ASSERT


ROOT = Path(__file__).absolute().parent.parent.parent
scripts.ensure_directory(ROOT / '.git')  # Sanity check


DEFAULT_FOREMAN = ROOT / 'shipyard' / 'scripts' / 'foreman.sh'
DEFAULT_BUILDER = ROOT / 'shipyard' / 'scripts' / 'builder'


with_foreman_argument = apps.with_decorators(
    apps.with_argument(
        '--foreman', metavar='PATH', type=Path, default=DEFAULT_FOREMAN,
        help='provide path to the foreman script (default %(default)s)',
    ),
    apps.with_argument(
        '--foreman-arg', metavar='ARG', action='append',
        help='add command-line argument to foreman script',
    ),
)


with_builder_argument = apps.with_decorators(
    apps.with_argument(
        '--builder', metavar='PATH', type=Path, default=DEFAULT_BUILDER,
        help='provide path to the builder script (default %(default)s)',
    ),
    apps.with_argument(
        '--builder-arg', metavar='ARG', action='append',
        help='add command-line argument to builder script',
    ),
)


with_argument_input = apps.with_argument(
    '--input-root', metavar='PATH', type=Path, action='append',
    help='add input root path',
)


class Builder:

    def __init__(self, args):
        self.builder = scripts.ensure_file(args.builder)
        self.builder_args = args.builder_arg or ()

    def build(self, label, extra_args=()):
        cmd = [self.builder, 'build', str(label)]
        cmd.extend(self.builder_args)
        cmd.extend(extra_args)
        scripts.execute(cmd)


class RuleIndex:

    def __init__(self, args):
        self.foreman = scripts.ensure_file(args.foreman)
        self.foreman_args = args.foreman_arg or ()
        self._build_data = None

    def load_from_labels(self, labels):
        """Load build data from labels."""
        cmd = [self.foreman, 'list']
        cmd.extend(map(str, labels))
        cmd.extend(self.foreman_args)
        stdout = scripts.execute(cmd, capture_stdout=True).stdout
        self._build_data = json.loads(stdout.decode('utf8'))

    def get_parameter(self, label, *, implicit_path=None):
        data = self._get_thing('parameters', label, implicit_path)
        return Parameter(
            label=Label.parse(data['label']),
            default=data.get('default'),
        )

    def get_rule(self, label, *, implicit_path=None):
        data = self._get_thing('rules', label, implicit_path)
        return Rule(
            label=Label.parse(data['label']),
            annotations=data['annotations'],
            all_dependencies=[
                Dependency(
                    label=Label.parse(dep['label']),
                )
                for dep in data['all_dependencies']
            ],
        )

    def _get_thing(self, kind, label, implicit_path):
        ASSERT.not_none(self._build_data)
        if isinstance(label, str):
            label = Label.parse(label, implicit_path=implicit_path)
        label_str = str(label)
        for thing in self._build_data['//%s' % label.path][kind]:
            if thing['label'] == label_str:
                return thing
        raise KeyError(label)

    def get_pod_name(self, rule_obj):
        pod_names = set()

        pod_parameter_label = rule_obj.annotations.get('pod-parameter')
        if pod_parameter_label is not None:
            pod_parameter = self.get_parameter(
                pod_parameter_label,
                implicit_path=rule_obj.label.path,
            )
            pod_names.add(pod_parameter.default['name'])

        pod_name = rule_obj.annotations.get('pod-name')
        if pod_name is not None:
            pod_names.add(pod_name)

        if len(pod_names) != 1:
            raise AssertionError(
                'expect exactly one pod name from annotation: %s' %
                sorted(pod_names)
            )

        return Label.parse(pod_names.pop())

    def get_volume_name(self, rule_obj):
        volume_parameter_label = rule_obj.annotations.get('volume-parameter')
        if volume_parameter_label is None:
            raise AssertionError(
                'expect volume name from annotation: {}'.format(rule_obj))
        volume_parameter = self.get_parameter(
            volume_parameter_label,
            implicit_path=rule_obj.label.path,
        )
        return Label.parse(volume_parameter.default['name'])


def find_default_path(input_roots, kind, label):
    for input_root in input_roots:
        path = (
            input_root / 'defaults' / kind / label.path /
            ('%s.yaml' % label.name)
        )
        if path.exists():
            return path
    return None


def find_input_path(input_roots, kind, label):
    ASSERT.in_(kind, ('image-data', 'volume-data'))
    for input_root in input_roots:
        input_path = Path(kind) / label.path / label.name
        if (input_root / input_path).exists():
            return input_root, input_path
    return None, None


Dependency = namedtuple('Dependency', [
    'label',
])


Parameter = namedtuple('Parameter', [
    'label',
    'default',
])


Rule = namedtuple('Rule', [
    'label',
    'annotations',
    'all_dependencies',
])


def get_build_image_rules(rules, build_pod_rule):
    _ensure_rule_type(build_pod_rule, 'build_pod')
    specify_pod_rule = get_specify_pod_rule(rules, build_pod_rule)
    return [
        rules.get_rule(
            dep_rule.annotations['build-image-rule'],
            implicit_path=dep_rule.label.path,
        )
        for dep_rule in _iter_specify_rules(rules, specify_pod_rule, 'image')
    ]


def get_specify_app_rule(rules, build_rule):
    return _get_specify_rule(rules, build_rule, 'app')


def get_specify_image_rule(rules, build_rule):
    return _get_specify_rule(rules, build_rule, 'image')


def get_specify_pod_rule(rules, build_rule):
    return _get_specify_rule(rules, build_rule, 'pod')


def _get_specify_rule(rules, build_rule, kind):
    for dep in build_rule.all_dependencies:
        dep_rule = rules.get_rule(dep.label)
        if dep_rule.annotations.get('rule-type') == 'specify_' + kind:
            return dep_rule
    raise ValueError('no specify_%s rule for %s' % (kind, build_rule))


def _iter_specify_rules(rules, build_rule, kind):
    for dep in build_rule.all_dependencies:
        dep_rule = rules.get_rule(dep.label)
        if dep_rule.annotations.get('rule-type') == 'specify_' + kind:
            yield dep_rule


def _ensure_rule_type(rule, rule_type):
    if rule.annotations.get('rule-type') != rule_type:
        raise ValueError('not a %s rule: %s' % (rule_type, rule))
