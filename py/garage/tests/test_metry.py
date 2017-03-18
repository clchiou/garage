import unittest

import logging

from garage import metry
from garage.metry.reporters.logging import LogReporter

from tests.utils import Any


class MetryTest(unittest.TestCase):

    def test_metry_tree(self):
        tree = metry.MetryTree()
        metry_abc = tree.get_metry('a.b.c')
        metry_abd = tree.get_metry('a.b.d')
        metry_abde = tree.get_metry('a.b.d.e')
        metry_root = tree.get_metry()

        self.assertIs(metry_abc, tree.get_metry('a.b.c'))
        self.assertIs(metry_abd, tree.get_metry('a.b.d'))
        self.assertIs(metry_abde, tree.get_metry('a.b.d.e'))
        self.assertIs(metry_root, tree.get_metry())

        metry_root.enabled = True
        metry_abd.enabled = False
        tree.initialize()

        self.assertIs(metry_abc, tree.get_metry('a.b.c'))
        self.assertIs(metry_abd, tree.get_metry('a.b.d'))
        self.assertIs(metry_abde, tree.get_metry('a.b.d.e'))
        self.assertIs(metry_root, tree.get_metry())

        self.assertTrue(metry_abc.enabled)
        self.assertFalse(metry_abd.enabled)
        self.assertFalse(metry_abde.enabled)
        self.assertTrue(metry_root.enabled)

        self.assertFalse(hasattr(metry_root, '_metry_tree'))
        self.assertFalse(hasattr(metry_abc, '_metry_tree'))
        self.assertFalse(hasattr(metry_abd, '_metry_tree'))
        self.assertFalse(hasattr(metry_abde, '_metry_tree'))

        with self.assertRaises(KeyError):
            tree.get_metry('x')

    def test_counter(self):
        measurements = []
        def report(metry_name, measure_name, data):
            measurements.append((metry_name, measure_name, data))

        tree = metry.MetryTree()

        m0 = metry.make_measure(
            tree, metry.measures.make_counter, 'c0')
        m1 = metry.make_measure(
            tree, metry.measures.make_counter, 'a.b.c', 'c1')

        root = tree.get_metry()
        root.enabled = True
        root.add_reporter(report)

        tree.initialize()

        m0()
        m1(10)
        self.assertListEqual(
            [
                (None, 'c0', (Any(float), 1, None)),
                ('a.b.c', 'c1', (Any(float), 10, None)),
            ],
            measurements,
        )

    def test_timer(self):
        measurements = []
        def report(metry_name, measure_name, data):
            measurements.append((metry_name, measure_name, data))

        tree = metry.MetryTree()
        timer = metry.make_measure(tree, metry.measures.make_timer, 'x', 't0')
        root = tree.get_metry()
        root.enabled = True
        root.add_reporter(report)
        tree.initialize()

        with timer.time() as cxt:
            cxt.stop()
            cxt.stop()
        self.assertListEqual(
            [
                ('x', 't0', (Any(float), None, Any(float))),
            ],
            measurements,
        )

        class MyError(Exception):
            pass
        @timer
        def foo():
            raise MyError
        try:
            foo()
        except MyError:
            pass
        else:
            self.fail()
        self.assertListEqual(
            [
                ('x', 't0', (Any(float), None, Any(float))),
                ('x', 't0', (Any(float), None, Any(float))),
            ],
            measurements,
        )

    def test_log_reporter(self):
        tree = metry.MetryTree()
        rater = metry.make_measure(tree, metry.measures.make_rater, 'r0')
        tree.get_metry().add_reporter(LogReporter(logging.getLogger()))
        tree.get_metry().enabled = True
        tree.initialize()
        with rater(1):
            pass


if __name__ == '__main__':
    unittest.main()
