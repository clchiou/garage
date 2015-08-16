import unittest

from garage.threads import utils


class UtilsTest(unittest.TestCase):

    def test_atomic_int(self):
        i = utils.AtomicInt()
        self.assertEqual(0, i.get_and_add(0))
        self.assertEqual(0, i.get_and_add(1))
        self.assertEqual(1, i.get_and_add(2))
        self.assertEqual(3, i.get_and_add(3))
        self.assertEqual(6, i.get_and_add(4))
        self.assertEqual(10, i.get_and_add(0))

    def test_atomic_set(self):
        s = utils.AtomicSet()
        self.assertFalse('x' in s)
        self.assertFalse(s.check_and_add('x'))
        self.assertTrue('x' in s)
        self.assertFalse(s.check_and_add('y'))
        self.assertTrue('y' in s)


if __name__ == '__main__':
    unittest.main()
