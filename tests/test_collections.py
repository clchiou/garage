import unittest

from garage.collections import (
    LoadingDict,
    Namespace,
    DictAsAttrs,
    FixedKeysDict,
    make_sorted_ordered_dict,
)


class CollectionsTest(unittest.TestCase):

    def test_loading_dict(self):
        ldict = LoadingDict(lambda key: key)
        self.assertDictEqual({}, ldict.data)
        self.assertEqual('k1', ldict['k1'])
        ldict['k2'] = 'value'
        self.assertEqual('value', ldict['k2'])
        self.assertDictEqual({'k1': 'k1', 'k2': 'value'}, ldict.data)

    def test_fixed_namespace(self):
        ns = Namespace(x=1, y=2)

        self.assertEqual(1, ns.x)
        self.assertEqual(2, ns.y)

        ns.x = 3
        self.assertEqual(3, ns.x)

        with self.assertRaises(AttributeError):
            ns.z
        with self.assertRaises(AttributeError):
            ns.z = 3

        with self.assertRaises(AttributeError):
            del ns.x
        with self.assertRaises(AttributeError):
            del ns.z

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

    def test_fixed_keys_dict(self):
        data = FixedKeysDict(a=1, b=2)

        self.assertEqual(1, data['a'])
        self.assertEqual(2, data['b'])
        self.assertNotIn('c', data)

        data['a'] = 3
        self.assertEqual(3, data['a'])

        with self.assertRaises(KeyError):
            data['c'] = 3

        with self.assertRaises(KeyError):
            del data['a']

    def test_sorted_ordered_dict(self):
        data = make_sorted_ordered_dict(b=2, a=1, c=3)
        self.assertListEqual(list('abc'), list(data.keys()))
        self.assertListEqual([1, 2, 3], list(data.values()))


if __name__ == '__main__':
    unittest.main()
