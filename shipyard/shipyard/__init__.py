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
]

from collections import namedtuple
from pathlib import Path
import json

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
        cmd = [self.builder, 'build', label]
        cmd.extend(self.builder_args)
        cmd.extend(extra_args)
        scripts.execute(cmd)


class RuleIndex:

    def __init__(self, args):
        self.foreman = scripts.ensure_file(args.foreman)
        self.foreman_args = args.foreman_arg or ()
        self._rule = None
        self._build_data = None

    def load_build_data(self, rule):
        cmd = [self.foreman, 'list', rule]
        cmd.extend(self.foreman_args)
        stdout = scripts.execute(cmd, capture_stdout=True).stdout
        self._build_data = json.loads(stdout.decode('utf8'))
        self._rule = rule

    def get_parameter(self, label):
        data = self._get_thing('parameters', label)
        return Parameter(
            label=data['label'],
            default=data.get('default'),
        )

    def get_rule(self, label):
        data = self._get_thing('rules', label)
        return Rule(
            label=data['label'],
            annotations=data['annotations'],
            all_dependencies=[
                Dependency(
                    label=dep['label'],
                )
                for dep in data['all_dependencies']
            ],
        )

    def _get_thing(self, kind, label):
        assert self._build_data is not None
        index = label.find(':')
        if index != -1:
            label_path = label[:index]
        else:
            # Assume label is relative to self._rule
            label_path = self._rule[:self._rule.index(':')]
            label = '%s:%s' % (label_path, label)
        for thing in self._build_data[label_path][kind]:
            if thing['label'] == label:
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
    if build_pod_rule.annotations.get('rule-type') != 'build_pod':
        raise ValueError('not build_pod rule: %s' % build_pod_rule)

    for dep in build_pod_rule.all_dependencies:
        dep_rule = rules.get_rule(dep.label)
        if dep_rule.annotations.get('rule-type') == 'specify_pod':
            break
    else:
        raise ValueError('no specify_pod rule for %s' % build_pod_rule)
    specify_pod_rule = dep_rule

    build_image_rules = []
    for dep in specify_pod_rule.all_dependencies:
        dep_rule = rules.get_rule(dep.label)
        if dep_rule.annotations.get('rule-type') == 'specify_image':
            rule = rules.get_rule(dep_rule.annotations['build-image-rule'])
            build_image_rules.append(rule)

    return build_image_rules
