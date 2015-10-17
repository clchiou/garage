"""Measure your application."""

__all__ = [
    'config',
    'counter',
]

import functools
import logging
import threading

from garage import asserts
from garage.collections import Trie

from . import measures


LOG = logging.getLogger(__name__)


ROOT_METRY_NAME = ''


class MetryTree:

    def __init__(self):
        self._configured = False
        self._trie = Trie()

    @staticmethod
    def _get_key(name):
        return name.split('.') if name else ()

    def get_metry(self, name=ROOT_METRY_NAME):
        key = self._get_key(name)
        try:
            metry = self._trie[key]
        except KeyError:
            if self._configured:
                raise
            metry = self._trie[key] = Metry(self, name)
        return metry

    def config(self):
        asserts.precond(not self._configured)
        for metry in self._trie.values():
            metry.config()
        self._configured = True

    def get_parents(self, metry):
        key = self._get_key(metry.name)
        parents = [metry for _, metry in self._trie.get_values(key)]
        return reversed(parents[:-1])


class Metry:

    def __init__(self, metry_tree, name):
        LOG.debug('create metry %r', name)
        self.name = name
        self._metry_tree = metry_tree
        self._configured = False
        self._enabled = None
        self._reporters = None
        self._measures_lock = threading.Lock()
        self._measures = {}

    @property
    def enabled(self):
        if self._enabled is not None:
            return self._enabled
        asserts.precond(not self._configured)
        for metry in self._metry_tree.get_parents(self):
            if metry._enabled is not None:
                return metry._enabled
        return False

    @enabled.setter
    def enabled(self, enabled):
        asserts.precond(not self._configured)
        self._enabled = enabled

    def get_or_add_measure(self, name, make):
        with self._measures_lock:
            measure = self._measures.get(name)
            if measure is None:
                measure = self._measures[name] = make(self, name)
            return measure

    def add_reporter(self, reporter):
        asserts.precond(not self._configured)
        if self._reporters is None:
            self._reporters = []
        self._reporters.append(reporter)

    def config(self):
        asserts.precond(not self._configured)
        for metry in self._metry_tree.get_parents(self):
            if self._enabled is None and metry._enabled is not None:
                self._enabled = metry._enabled
            if self._reporters is None and metry._reporters is not None:
                self._reporters = metry._reporters
            if self._enabled is not None and self._reporters is not None:
                break
        if self._enabled is None:
            self._enabled = False
        self._configured = True
        del self._metry_tree
        LOG.debug('metry %r is configured with enabled=%s',
                  self.name, self._enabled)

    def measure(self, name, data):
        asserts.precond(self._configured)
        if self._enabled and self._reporters:
            for reporter in self._reporters:
                reporter(self.name, name, data)


def make_measure(metry_tree, make, *args):
    try:
        metry_name, measure_name = args
    except ValueError:
        metry_name, measure_name = ROOT_METRY_NAME, args[0]
    metry = metry_tree.get_metry(metry_name)
    return metry.get_or_add_measure(measure_name, make)


METRY_TREE = MetryTree()


config = METRY_TREE.config
counter = functools.partial(make_measure, METRY_TREE, measures.make_counter)
