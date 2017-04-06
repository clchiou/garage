"""\
Helpers for build scripts under `scripts` directory (these are not build
rule templates for helping you write build rules).
"""

__all__ = [
    'Builder',
    'RuleIndex',
    'argument_foreman',
    'argument_builder',
    'get_build_image_rules',
    'get_specify_app_rule',
    'get_specify_image_rule',
    'get_specify_pod_rule',
]

from collections import namedtuple
from pathlib import Path
import json

from foreman import Label

from garage import cli
from garage import scripts


ROOT = Path(__file__).absolute().parent.parent.parent
scripts.ensure_directory(ROOT / '.git')  # Sanity check


DEFAULT_FOREMAN = ROOT / 'shipyard' / 'scripts' / 'foreman.sh'
DEFAULT_BUILDER = ROOT / 'shipyard' / 'scripts' / 'builder'


argument_foreman = cli.combine_decorators(
    cli.argument(
        '--foreman', metavar='PATH', type=Path, default=DEFAULT_FOREMAN,
        help='provide path to the foreman script (default %(default)s)',
    ),
    cli.argument(
        '--foreman-arg', metavar='ARG', action='append',
        help='add command-line argument to foreman script',
    ),
)


argument_builder = cli.combine_decorators(
    cli.argument(
        '--builder', metavar='PATH', type=Path, default=DEFAULT_BUILDER,
        help='provide path to the builder script (default %(default)s)',
    ),
    cli.argument(
        '--builder-arg', metavar='ARG', action='append',
        help='add command-line argument to builder script',
    ),
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
        self._label_path = None

    def load_build_data(self, rule):
        if isinstance(rule, str):
            self._label_path = Label.parse(rule).path
        else:
            self._label_path = rule.path
        cmd = [self.foreman, 'list', str(rule)]
        cmd.extend(self.foreman_args)
        stdout = scripts.execute(cmd, capture_stdout=True).stdout
        self._build_data = json.loads(stdout.decode('utf8'))

    def get_parameter(self, label):
        data = self._get_thing('parameters', label)
        return Parameter(
            label=Label.parse(data['label']),
            default=data.get('default'),
        )

    def get_rule(self, label):
        data = self._get_thing('rules', label)
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

    def _get_thing(self, kind, label):
        assert self._build_data is not None
        if isinstance(label, str):
            label = Label.parse(label, implicit_path=self._label_path)
        label_str = str(label)
        for thing in self._build_data['//%s' % label.path][kind]:
            if thing['label'] == label_str:
                return thing
        raise KeyError(label)


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
        rules.get_rule(dep_rule.annotations['build-image-rule'])
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
