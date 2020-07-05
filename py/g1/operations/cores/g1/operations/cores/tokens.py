"""Manage tokens.

A token has a name and a value.  Tokens are grouped by their name, and
can be assigned to pods.  For now we make the following restrictions:

* Only one token from a group can be assigned to the same pod.
* Only str-typed token values.
"""

__all__ = [
    'init',
    'make_tokens_database',
]

import contextlib
import dataclasses
import logging
import typing
from pathlib import Path

from g1.bases import collections as g1_collections
from g1.bases.assertions import ASSERT
from g1.containers import models as ctr_models
from g1.files import locks
from g1.texts import jsons

from . import bases
from . import models

LOG = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class Tokens:

    @dataclasses.dataclass(frozen=True)
    class Definition:
        """Definition of tokens."""
        kind: str
        args: typing.List[typing.Union[int, str]]

        def __post_init__(self):
            ASSERT.in_(self.kind, ('range', 'values'))
            if self.kind == 'range':
                ASSERT.equal(len(self.args), 2)
                ASSERT.all(self.args, lambda arg: isinstance(arg, int))
                ASSERT.less_or_equal(self.args[0], self.args[1])
            else:
                ASSERT.equal(self.kind, 'values')
                ASSERT.all(self.args, lambda arg: isinstance(arg, str))

        def validate_assigned_values(self, assigned_values):
            ASSERT.all(assigned_values, lambda value: isinstance(value, str))
            if self.kind == 'range':
                ASSERT.unique(assigned_values)
                ASSERT.all(
                    assigned_values,
                    lambda value: self.args[0] <= int(value) < self.args[1],
                )
            else:
                ASSERT.equal(self.kind, 'values')
                ASSERT.issubset(
                    g1_collections.Multiset(assigned_values),
                    g1_collections.Multiset(self.args),
                )
            return assigned_values

        def next_available(self, assigned_values):
            if self.kind == 'range':
                assigned_value_set = frozenset(map(int, assigned_values))
                if assigned_value_set:
                    value = max(assigned_value_set) + 1
                    if value < self.args[1]:
                        return str(value)
                for value in range(*self.args):
                    if value not in assigned_value_set:
                        return str(value)
            else:
                ASSERT.equal(self.kind, 'values')
                candidates = g1_collections.Multiset(self.args)
                candidates -= g1_collections.Multiset(assigned_values)
                if candidates:
                    return next(iter(candidates))
            return ASSERT.unreachable(
                'no value available: {} {}', self, assigned_values
            )

    @dataclasses.dataclass(frozen=True)
    class Assignment:
        """Assignment of a token to a pod."""
        pod_id: str
        value: str

        def __post_init__(self):
            ctr_models.validate_pod_id(self.pod_id)

    definitions: typing.MutableMapping[str, Definition]
    assignments: typing.MutableMapping[str, typing.List[Assignment]]

    def __post_init__(self):
        self.check_invariants()

    def check_invariants(self):
        ASSERT.all(self.definitions, models.validate_token_name)
        for name, assignments in self.assignments.items():
            models.validate_token_name(name)
            # A pod can only have at most one token from one group.
            ASSERT.unique(assignments, lambda a: a.pod_id)
            ASSERT.getitem(self.definitions, name).validate_assigned_values([
                a.value for a in assignments
            ])

    @classmethod
    def load(cls, path):
        return jsons.load_dataobject(cls, path)

    def dump(self, path):
        jsons.dump_dataobject(self, path)

    def has_definition(self, name):
        return name in self.definitions

    def add_definition(self, name, definition):
        models.validate_token_name(name)
        ASSERT.isinstance(definition, self.Definition)
        ASSERT.setitem(self.definitions, name, definition)

    def update_definition(self, name, definition):
        models.validate_token_name(name)
        ASSERT.isinstance(definition, self.Definition)
        # Validate the new definition before updating.
        definition.validate_assigned_values([
            a.value for a in self.assignments[name]
        ])
        self.definitions[name] = definition

    def remove_definition(self, name):
        ASSERT.contains(self.definitions, name).pop(name)
        self.assignments.pop(name, None)

    def iter_pod_ids(self, name):
        for assignment in ASSERT.getitem(self.assignments, name):
            yield assignment.pod_id

    def assign(self, name, pod_id, value=None):
        """Assign a token to a pod."""
        ASSERT.predicate(name, self.has_definition)
        ctr_models.validate_pod_id(pod_id)
        definition = self.definitions[name]
        assignments = self.assignments.setdefault(name, [])
        # A pod can only have at most one token from one group.
        ASSERT.not_any(assignments, lambda a: a.pod_id == pod_id)
        assigned_values = [a.value for a in assignments]
        if value is None:
            value = definition.next_available(assigned_values)
        else:
            assigned_values.append(value)
            definition.validate_assigned_values(assigned_values)
        assignments.append(self.Assignment(pod_id=pod_id, value=value))
        LOG.info('tokens assign: %s %s %s', pod_id, name, value)
        return value

    def unassign_all(self, pod_id):
        """Unassign tokens from a pod."""
        ctr_models.validate_pod_id(pod_id)
        self._remove('unassign', pod_id.__eq__)

    def cleanup(self, active_pod_ids):
        self._remove('cleanup', lambda pod_id: pod_id not in active_pod_ids)

    def _remove(self, cmd, predicate):
        # Make a copy of dict keys because we are modifying it.
        for name in tuple(self.assignments):
            to_keep = []
            for assignment in self.assignments[name]:
                if predicate(assignment.pod_id):
                    LOG.info(
                        'tokens %s: %s %s %s',
                        cmd,
                        assignment.pod_id,
                        name,
                        assignment.value,
                    )
                else:
                    to_keep.append(assignment)
            if not to_keep:
                self.assignments.pop(name)
            else:
                self.assignments[name] = to_keep


class TokensDatabase:

    @staticmethod
    def init(path):
        if path.exists():
            LOG.info('skip: tokens init: %s', path)
            return
        LOG.info('tokens init: %s', path)
        Tokens(definitions={}, assignments={}).dump(path)
        bases.set_file_attrs(path)

    def __init__(self, path):
        self.path = ASSERT.predicate(path, Path.exists)

    def get(self):
        with locks.acquiring_shared(self.path):
            return Tokens.load(self.path)

    @contextlib.contextmanager
    def writing(self):
        with locks.acquiring_exclusive(self.path):
            tokens = Tokens.load(self.path)
            yield tokens
            # Just a sanity check before we write back changes.
            tokens.check_invariants()
            # No finally-block here because we do not want to write back
            # changes on error.
            LOG.debug('tokens writing: %s', tokens)
            tokens.dump(self.path)

    def cleanup(self, pod_ops_dirs):
        with pod_ops_dirs.listing_ops_dirs() as active_ops_dirs:
            active_pod_ids = frozenset(
                config.pod_id
                for ops_dir in active_ops_dirs
                for config in ops_dir.metadata.systemd_unit_configs
            )
        with self.writing() as tokens:
            tokens.cleanup(active_pod_ids)


def init():
    tokens_path = _get_tokens_path()
    TokensDatabase.init(tokens_path)


def make_tokens_database():
    return TokensDatabase(_get_tokens_path())


def _get_tokens_path():
    return bases.get_repo_path() / models.REPO_TOKENS_FILENAME
