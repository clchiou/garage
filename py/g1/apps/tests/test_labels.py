import unittest

from g1.apps import labels


class LabelTest(unittest.TestCase):

    def test_label(self):
        l = labels.Label('foo.bar', 'spam.egg')
        self.assertEqual(l, 'foo.bar:spam.egg')
        self.assertEqual(hash(l), hash('foo.bar:spam.egg'))
        self.assertEqual(str(l), 'foo.bar:spam.egg')
        self.assertEqual(repr(l), repr('foo.bar:spam.egg'))

        l2 = labels.Label('foo.bar', 'spam.egg')
        self.assertIsNot(l, l2)
        self.assertEqual(l, l2)
        self.assertEqual(hash(l), hash(l2))

        l3 = labels.Label('foo.bar', 'spam.egg_')
        self.assertIsNot(l, l3)
        self.assertNotEqual(l, l3)
        self.assertNotEqual(hash(l), hash(l3))

    def test_label_format(self):

        for module_path, object_path in (
            ('foo', 'bar'),
            ('_f_9_o_.x.y.z', 'b.a.r'),
        ):
            with self.subTest((module_path, object_path)):
                labels.Label(module_path, object_path)

        error = r'expect.*is_path'
        for module_path, object_path in (
            # Empty path.
            ('', ''),
            ('foo', ''),
            ('', 'bar'),
            # Empty path part.
            ('foo.', 'bar'),
            ('foo', 'bar.'),
            ('.foo', 'bar'),
            ('foo', '.bar'),
            # Illegal characters.
            ('0foo', 'bar'),
            ('foo', '0bar'),
            ('foo/', 'bar'),
            ('foo', 'bar/'),
        ):
            with self.subTest((module_path, object_path)):
                with self.assertRaisesRegex(AssertionError, error):
                    labels.Label(module_path, object_path)

    def test_make_labels(self):
        names = labels.make_labels('foo.bar', 'x', 'y', z='p.q')
        self.assertEqual(
            names._asdict(),
            {
                'x': labels.Label('foo.bar', 'x'),
                'y': labels.Label('foo.bar', 'y'),
                'z': labels.Label('foo.bar', 'p.q'),
            },
        )
        self.assertEqual(names.x, labels.Label('foo.bar', 'x'))
        self.assertEqual(names.y, labels.Label('foo.bar', 'y'))
        self.assertEqual(names.z, labels.Label('foo.bar', 'p.q'))

        n2 = labels.make_labels('spam.egg', 'p', **names._asdict())
        self.assertEqual(
            n2._asdict(),
            {
                'p': labels.Label('spam.egg', 'p'),
                'x': labels.Label('foo.bar', 'x'),
                'y': labels.Label('foo.bar', 'y'),
                'z': labels.Label('foo.bar', 'p.q'),
            },
        )


if __name__ == '__main__':
    unittest.main()
