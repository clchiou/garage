import unittest
import unittest.mock

from g1.bases import labels


class LabelTest(unittest.TestCase):

    def test_label(self):
        l = labels.Label('foo.bar', 'spam.egg')
        self.assertEqual(l, 'foo.bar:spam.egg')
        self.assertEqual(hash(l), hash('foo.bar:spam.egg'))
        self.assertEqual(str(l), 'foo.bar:spam.egg')
        self.assertEqual(repr(l), repr('foo.bar:spam.egg'))
        self.assertEqual(l.module_path, 'foo.bar')
        self.assertEqual(l.object_path, 'spam.egg')

        self.assertEqual(labels.Label.parse('foo.bar:spam.egg'), l)

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
            ('foo.bar', 'a[1].b[22].c[333]'),
        ):
            with self.subTest((module_path, object_path)):
                labels.Label(module_path, object_path)

        error = r'expect.*fullmatch'
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
            # Illegal identifier characters.
            ('0foo', 'bar'),
            ('foo', '0bar'),
            ('foo/', 'bar'),
            ('foo', 'bar/'),
            # Incorrect element index.
            ('foo', 'bar[]'),
            ('foo', 'bar[x]'),
            ('foo', 'bar.[0]'),
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

    def test_make_nested_labels(self):

        self.assertEqual(
            flatten(
                labels.make_nested_labels(
                    'foo.bar',
                    # Strings are iterables, too (this may be confusing
                    # sometimes).
                    ('a', ('b', 'x'), ('c', (('y', 'z'), ))),
                ),
            ),
            (
                ('a', 'foo.bar:a'),
                ('b.x', 'foo.bar:b.x'),
                ('c.y.z', 'foo.bar:c.y.z'),
            ),
        )

        self.assertEqual(
            flatten(
                labels.make_nested_labels(
                    'foo.bar',
                    (('a', ('x', 'y', 'z')), ),
                ),
            ),
            (
                ('a.x', 'foo.bar:a.x'),
                ('a.y', 'foo.bar:a.y'),
                ('a.z', 'foo.bar:a.z'),
            ),
        )

    @unittest.mock.patch(labels.__name__ + '.importlib')
    def test_load_global(self, importlib_mock):

        module_mock = importlib_mock.import_module.return_value
        module_mock.X = 'hello world'
        module_mock.Y = (42, (43, 44))

        for label_str, expect in (
            ('foo.bar:X', 'hello world'),
            ('foo.bar:X.__class__', str),
            ('foo.bar:Y[0]', 42),
            ('foo.bar:Y[1][0]', 43),
        ):
            with self.subTest(label_str):
                self.assertEqual(labels.load_global(label_str), expect)


def flatten(root):

    names = []

    def _flatten(node):
        for n, v in node._entries.items():
            names.append(n)
            if isinstance(v, labels.Label):
                yield '.'.join(names), v
            else:
                yield from _flatten(v)
            names.pop()

    return tuple(_flatten(root))


if __name__ == '__main__':
    unittest.main()
