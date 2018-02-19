"""Measure your application."""

__all__ = [
    'add_reporter',
    'enable',
    'initialize',

    'counter',
    'rater',
    'timer',
]

import functools
import logging
import threading

from garage.assertions import ASSERT
from garage.collections import Trie

from . import measures


LOG = logging.getLogger(__name__)


ROOT_METRY_NAME = None


class MetryTree:

    def __init__(self):
        self._initialized = False
        self._trie = Trie()

    @staticmethod
    def _get_key(name):
        return name.split('.') if name else ()

    def get_metry(self, name=ROOT_METRY_NAME):
        key = self._get_key(name)
        try:
            metry = self._trie[key]
        except KeyError:
            if self._initialized:
                raise
            metry = self._trie[key] = Metry(self, name)
        return metry

    def initialize(self):
        ASSERT.false(self._initialized)
        for metry in self._trie.values():
            metry.initialize()
        self._initialized = True

    def get_parents(self, metry):
        key = self._get_key(metry.name)
        parents = [metry for _, metry in self._trie.get_values(key)]
        return reversed(parents[:-1])


class Metry:

    def __init__(self, metry_tree, name):
        LOG.debug('create metry %r', name)
        self.name = name
        self._metry_tree = metry_tree
        self._initialized = False
        self._enabled = None
        self._reporters = None
        self._measures_lock = threading.Lock()
        self._measures = {}

    @property
    def enabled(self):
        if self._enabled is not None:
            return self._enabled
        ASSERT.false(self._initialized)
        for metry in self._metry_tree.get_parents(self):
            if metry._enabled is not None:
                return metry._enabled
        return False

    @enabled.setter
    def enabled(self, enabled):
        ASSERT.false(self._initialized)
        self._enabled = enabled

    def get_or_add_measure(self, name, make):
        with self._measures_lock:
            measure = self._measures.get(name)
            if measure is None:
                measure = self._measures[name] = make(self, name)
            return measure

    def add_reporter(self, reporter):
        ASSERT.false(self._initialized)
        if self._reporters is None:
            self._reporters = []
        self._reporters.append(reporter)

    def initialize(self):
        ASSERT.false(self._initialized)
        for metry in self._metry_tree.get_parents(self):
            if self._enabled is None and metry._enabled is not None:
                self._enabled = metry._enabled
            if self._reporters is None and metry._reporters is not None:
                self._reporters = metry._reporters
            if self._enabled is not None and self._reporters is not None:
                break
        if self._enabled is None:
            self._enabled = False
        self._initialized = True
        del self._metry_tree
        LOG.debug('metry %r is configured with enabled=%s',
                  self.name, self._enabled)

    def measure(self, name, measurement):
        if self._enabled and self._reporters:
            for reporter in self._reporters:
                reporter(self.name, name, measurement)


METRY_TREE = MetryTree()


def make_measure(metry_tree, make, *args):
    try:
        metry_name, measure_name = args
    except ValueError:
        metry_name, measure_name = ROOT_METRY_NAME, args[0]
    metry = metry_tree.get_metry(metry_name)
    return metry.get_or_add_measure(measure_name, make)


def add_reporter(*args):
    try:
        metry_name, reporter = args
    except ValueError:
        metry_name, reporter = ROOT_METRY_NAME, args[0]
    LOG.debug('add reporter to metry %r', metry_name)
    METRY_TREE.get_metry(metry_name).add_reporter(reporter)


def enable(metry_name=ROOT_METRY_NAME, enabled=True):
    LOG.debug('set enabled of metry %r to %r', metry_name, enabled)
    METRY_TREE.get_metry(metry_name).enabled = enabled


initialize = METRY_TREE.initialize


counter = functools.partial(make_measure, METRY_TREE, measures.make_counter)
rater = functools.partial(make_measure, METRY_TREE, measures.make_rater)
timer = functools.partial(make_measure, METRY_TREE, measures.make_timer)
