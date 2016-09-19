import unittest

import sys
import os.path

# HACK: Add shipyard and foreman to path.
sys.path.append(os.path.abspath(os.path.join(
    os.path.dirname(__file__), '..')))
sys.path.append(os.path.abspath(os.path.join(
    os.path.dirname(__file__), '../../../py/foreman')))

from shipyard import build_dict


class BuildDictTest(unittest.TestCase):

    def test_write_in_place(self):
        data = {}
        build_dict(data).set('x', 1)
        self.assertEqual({'x': 1}, data)

    def test_if_block(self):
        self.assertEqual(
            {'w': 1, 'x': 2, 'y': 3, 'z': 4},
            (build_dict()
             .if_(True) .set('w', 1).elif_(True) .set('w', 2).elif_(True) .set('w', 3).else_().set('w', 4).end_if()
             .if_(False).set('x', 1).elif_(True) .set('x', 2).elif_(True) .set('x', 3).else_().set('x', 4).end_if()
             .if_(False).set('y', 1).elif_(False).set('y', 2).elif_(True) .set('y', 3).else_().set('y', 4).end_if()
             .if_(False).set('z', 1).elif_(False).set('z', 2).elif_(False).set('z', 3).else_().set('z', 4).end_if()
             .dict),
        )

        with self.assertRaises(AssertionError):
            build_dict().elif_(True)
        with self.assertRaises(AssertionError):
            build_dict().else_()
        with self.assertRaises(AssertionError):
            build_dict().end_if()

        with self.assertRaises(AssertionError):
            build_dict().if_(True).if_(True)
        with self.assertRaises(AssertionError):
            build_dict().if_(True).elif_(True).if_(True)
        with self.assertRaises(AssertionError):
            build_dict().if_(True).else_().elif_(True)


if __name__ == '__main__':
    unittest.main()
