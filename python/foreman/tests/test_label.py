import unittest

from pathlib import PurePosixPath

from foreman import Label


class LabelTest(unittest.TestCase):

    def assertLabel(self, path, name, label):
        self.assertEqual(path, str(label.path))
        self.assertEqual(name, str(label.name))

    def test_label(self):
        self.assertLabel('x/y/z', 'a/b/c', Label.parse('//x/y/z:a/b/c'))
        with self.assertRaises(ValueError):
            Label.parse('//x/y/z')

        self.assertLabel(
            'x/y/z', 'a/b/c',
            Label.parse(':a/b/c', implicit_path=PurePosixPath('x/y/z')))
        with self.assertRaises(ValueError):
            Label.parse('a/b/c')

        # Test Label.__eq__ and __hash__.
        self.assertEqual(Label.parse('//x:y'), Label.parse('//x:y'))
        self.assertNotEqual(Label.parse('//x:y'), Label.parse('//x:z'))
        self.assertNotEqual(Label.parse('//w:y'), Label.parse('//x:y'))
        self.assertEqual(
            hash(Label.parse('//x:y')), hash(Label.parse('//x:y')))
        self.assertNotEqual(
            hash(Label.parse('//x:y')), hash(Label.parse('//x:z')))
        self.assertNotEqual(
            hash(Label.parse('//w:y')), hash(Label.parse('//x:y')))


if __name__ == '__main__':
    unittest.main()
