import unittest

from garage import metry


class MetryTest(unittest.TestCase):

    def test_metry_tree(self):
        tree = metry.MetryTree()
        metry_abc = tree.get_metry('a.b.c')
        metry_abd = tree.get_metry('a.b.d')
        metry_abde = tree.get_metry('a.b.d.e')
        metry_root = tree.get_metry('')

        self.assertIs(metry_abc, tree.get_metry('a.b.c'))
        self.assertIs(metry_abd, tree.get_metry('a.b.d'))
        self.assertIs(metry_abde, tree.get_metry('a.b.d.e'))
        self.assertIs(metry_root, tree.get_metry(''))

        metry_root.enabled = True
        metry_abd.enabled = False
        tree.config()

        self.assertIs(metry_abc, tree.get_metry('a.b.c'))
        self.assertIs(metry_abd, tree.get_metry('a.b.d'))
        self.assertIs(metry_abde, tree.get_metry('a.b.d.e'))
        self.assertIs(metry_root, tree.get_metry(''))

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


if __name__ == '__main__':
    unittest.main()
