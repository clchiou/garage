"""Manage tokens.

A token has a name and a value.  Tokens are grouped by their name, and
can be assigned to pods.  A pod can acquire multiple tokens from the
same group; that is, token-to-pod is a many-to-one relationship.
"""

__all__ = [
    'init',
    'load_active_pod_ids',
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
        """Definition of tokens.

        Two kinds of definitions are supported:
        * Enumeration token values.
        * Range of token values.
        """
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
            """Validate assigned values.

            * No duplicated assignments.
            * Assigned values are a subset of defined values.
            """
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
                        # NOTE: We allow only str-typed token values.
                        return str(value)
                for value in range(*self.args):
                    if value not in assigned_value_set:
                        # NOTE: We allow only str-typed token values.
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
        """Assignment of a token to a pod.

        NOTE: For now we do not guarantee uniqueness among assignment
        names, even within assignments of the same pod.
        """
        pod_id: str
        name: str
        value: str

        def __post_init__(self):
            ctr_models.validate_pod_id(self.pod_id)

    # Map from token name to definition.
    definitions: typing.MutableMapping[str, Definition]
    # Map from token name to list of assignments.
    assignments: typing.MutableMapping[str, typing.List[Assignment]]

    def __post_init__(self):
        self.check_invariants()

    def check_invariants(self):
        ASSERT.all(self.definitions, models.validate_token_name)
        for token_name, assignments in self.assignments.items():
            models.validate_token_name(token_name)
            ASSERT.getitem(self.definitions, token_name)\
            .validate_assigned_values([a.value for a in assignments])

    @classmethod
    def load(cls, path):
        return jsons.load_dataobject(cls, path)

    def dump(self, path):
        jsons.dump_dataobject(self, path)

    def has_definition(self, token_name):
        return token_name in self.definitions

    def add_definition(self, token_name, definition):
        models.validate_token_name(token_name)
        ASSERT.isinstance(definition, self.Definition)
        ASSERT.setitem(self.definitions, token_name, definition)

    def update_definition(self, token_name, definition):
        models.validate_token_name(token_name)
        ASSERT.isinstance(definition, self.Definition)
        # Validate the new definition before updating.
        definition.validate_assigned_values([
            a.value for a in self.assignments[token_name]
        ])
        self.definitions[token_name] = definition

    def remove_definition(self, token_name):
        ASSERT.contains(self.definitions, token_name).pop(token_name)
        self.assignments.pop(token_name, None)

    def iter_pod_ids(self, token_name):
        """Iterate id of pods that have acquired this token group."""
        for assignment in self.assignments.get(token_name, ()):
            yield assignment.pod_id

    def assign(self, token_name, pod_id, name, value=None):
        """Assign a token to a pod."""
        ASSERT.predicate(token_name, self.has_definition)
        ctr_models.validate_pod_id(pod_id)
        definition = self.definitions[token_name]
        assignments = self.assignments.setdefault(token_name, [])
        assigned_values = [a.value for a in assignments]
        if value is None:
            value = definition.next_available(assigned_values)
        else:
            assigned_values.append(value)
            definition.validate_assigned_values(assigned_values)
        assignment = self.Assignment(pod_id=pod_id, name=name, value=value)
        assignments.append(assignment)
        LOG.info('tokens assign: %s %r', token_name, assignment)
        return value

    def unassign(self, token_name, pod_id, name):
        """Unassign a token from a pod.

        NOTE: For now we do not guarantee uniqueness among assignment
        names, and this method will unassign **all** matched assignment
        names.
        """
        ASSERT.predicate(token_name, self.has_definition)
        ctr_models.validate_pod_id(pod_id)
        self._remove(
            'unassign',
            lambda t, a:
            (t == token_name and a.pod_id == pod_id and a.name == name),
        )

    def unassign_all(self, pod_id):
        """Unassign tokens from a pod."""
        ctr_models.validate_pod_id(pod_id)
        self._remove('unassign_all', lambda _, a: a.pod_id == pod_id)

    def cleanup(self, active_pod_ids):
        """Unassign tokens from removed pods."""
        self._remove('cleanup', lambda _, a: a.pod_id not in active_pod_ids)

    def _remove(self, cmd, predicate):
        # Make a copy of dict keys because we are modifying it.
        for token_name in tuple(self.assignments):
            to_keep = []
            for assignment in self.assignments[token_name]:
                if predicate(token_name, assignment):
                    LOG.info(
                        'tokens %s: %s %s %s',
                        cmd,
                        assignment.pod_id,
                        token_name,
                        assignment.value,
                    )
                else:
                    to_keep.append(assignment)
            if not to_keep:
                self.assignments.pop(token_name)
            else:
                self.assignments[token_name] = to_keep


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
        active_pod_ids = load_active_pod_ids(pod_ops_dirs)
        with self.writing() as tokens:
            tokens.cleanup(active_pod_ids)


def init():
    tokens_path = _get_tokens_path()
    TokensDatabase.init(tokens_path)


def make_tokens_database():
    return TokensDatabase(_get_tokens_path())


def _get_tokens_path():
    return bases.get_repo_path() / models.REPO_TOKENS_FILENAME


def load_active_pod_ids(pod_ops_dirs):
    """Return active pod ids as a set, including the host id."""
    with pod_ops_dirs.listing_ops_dirs() as active_ops_dirs:
        active_pod_ids = set(
            config.pod_id
            for ops_dir in active_ops_dirs
            for config in ops_dir.metadata.systemd_unit_configs
        )
    active_pod_ids.add(ctr_models.read_host_pod_id())
    return active_pod_ids
