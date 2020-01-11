import unittest
import unittest.mock

from g1.apps import parameters
from g1.bases import labels


class NamespaceTest(unittest.TestCase):

    def test_setattr_error(self):
        with self.assertRaises(ValueError):
            parameters.Namespace(_x=1)

    def test_doc(self):
        n = parameters.Namespace('doc', x=1)
        self.assertEqual(n._doc, 'doc')
        self.assertEqual(n.x, 1)


class ParameterTest(unittest.TestCase):

    def setUp(self):
        unittest.mock.patch('g1.apps.parameters.INITIALIZED', True).start()

    def tearDown(self):
        unittest.mock.patch.stopall()

    def test_write_after_read(self):
        p = parameters.Parameter(0)
        self.assertEqual(p.get(), 0)
        with self.assertRaises(AssertionError):
            p.set(0)

    def test_incorrect_type(self):
        p = parameters.Parameter(0)

        with self.assertRaises(AssertionError):
            p.set('')

        p.set(1)
        self.assertEqual(p.get(), 1)

    def test_validator(self):
        p = parameters.Parameter(0, validator=lambda x: x < 1)
        self.assertEqual(p._value, 0)
        with self.assertRaises(AssertionError):
            p.set(1)
        self.assertEqual(p._value, 0)
        p.set(-1)
        self.assertEqual(p._value, -1)


class IterParametersTest(unittest.TestCase):

    def test_iter_parameters(self):
        n = parameters.Namespace(
            a=parameters.Parameter(1),
            m=parameters.Namespace(
                p=parameters.Parameter(4),
                q=parameters.Parameter(5),
            ),
            b=parameters.Parameter(2),
            c=parameters.Parameter(3),
        )
        self.assertEqual(
            list(parameters.iter_parameters('X', n)),
            [
                (labels.Label('X', 'a'), n.a),
                (labels.Label('X', 'm.p'), n.m.p),
                (labels.Label('X', 'm.q'), n.m.q),
                (labels.Label('X', 'b'), n.b),
                (labels.Label('X', 'c'), n.c),
            ],
        )


class LoadConfigForestTest(unittest.TestCase):

    def setUp(self):
        self.root = parameters.Namespace(
            a=parameters.Namespace(
                b=parameters.Namespace(
                    c=parameters.Namespace(d=parameters.Parameter(0)),
                ),
            ),
        )

    def test_load_config_tree(self):
        self.assertEqual(self.root.a.b.c.d._value, 0)
        parameters.load_config_forest(
            {
                'foo.bar': {
                    'a.b': {
                        'c': {
                            'd': 1,
                        },
                    },
                },
            },
            {'foo.bar': self.root},
        )
        self.assertEqual(self.root.a.b.c.d._value, 1)

    def test_wrong_module_path(self):
        with self.assertRaises(KeyError):
            parameters.load_config_forest(
                {
                    'foo.barxxx': {
                        'a.b': {
                            'c': {
                                'd': 1,
                            },
                        },
                    },
                },
                {'foo.bar': self.root},
            )

    def test_wrong_object_path(self):
        with self.assertRaises(AttributeError):
            parameters.load_config_forest(
                {
                    'foo.bar': {
                        'a.b': {
                            'cxxx': {
                                'd': 1,
                            },
                        },
                    },
                },
                {'foo.bar': self.root},
            )


if __name__ == '__main__':
    unittest.main()
