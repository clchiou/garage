import unittest

from garage.collections import DictAsAttrs
from garage.collections import FixedKeysDict


class TestDictAsAttrs(unittest.TestCase):

    def test_dict_as_attrs(self):
        attrs = DictAsAttrs({'y': 1})
        self.assertEqual(1, attrs.y)
        self.assertFalse(hasattr(attrs, 'x'))
        attrs.x = 2
        self.assertEqual(2, attrs.x)
        del attrs.y
        self.assertFalse(hasattr(attrs, 'y'))
        attrs.z = 3
        self.assertListEqual(['x', 'z'], dir(attrs))


class TestFixedKeysDict(unittest.TestCase):

    def test_fixed_keys_dict(self):
        data = FixedKeysDict(a=1, b=2)
        self.assertEqual(1, data['a'])
        self.assertEqual(2, data['b'])
        self.assertNotIn('c', data)

        data['a'] = 3
        self.assertEqual(3, data['a'])

        self.assertRaises(KeyError, data.update, [('c', 3)])
        self.assertRaises(NotImplementedError, data.pop, 'a')


if __name__ == '__main__':
    unittest.main()
