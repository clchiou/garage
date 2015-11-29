import unittest

from types import SimpleNamespace

from garage import models


POINT_MODEL = models.Model(
    'POINT_MODEL',
    models.Field('x'),
    models.Field('y'),
)


class ModelsTest(unittest.TestCase):

    def test_leading_underscore(self):
        with self.assertRaises(TypeError):
            models.Model('_m')
        with self.assertRaises(TypeError):
            models.Field('_f')

    def test_ref(self):
        refs = models.Refs()

        ref = refs.ref('p')
        with refs as context:
            context['p'] = p = SimpleNamespace()
            self.assertEqual(p, ref.deref())

        ref = refs.ref('p.x')
        with refs as context:
            context['p'] = p = SimpleNamespace()
            p.x = 1
            self.assertEqual(1, ref.deref())

        ref = refs.ref('q.y.y')
        with refs as context:
            context['q'] = q = SimpleNamespace()
            q.y = SimpleNamespace()
            q.y.y = 2
            self.assertEqual(2, ref.deref())

        with self.assertRaises(AttributeError):
            ref.deref()

        with refs as context:
            context['p'] = SimpleNamespace()
            with self.assertRaises(AttributeError):
                refs.ref('p.z').deref()

    def test_auto_deref(self):
        refs = models.Refs()
        model = models.Model(
            'model',
            models.Field('field', ref=refs.ref('x')),
            ref=refs.ref('y'),
        )
        refs.context['x'] = 1
        refs.context['y'] = 2
        self.assertEqual(1, model.f.field.a.ref)
        self.assertEqual(2, model.a.ref)


    def test_as_dict(self):
        Point = models.make_as_namespace(POINT_MODEL)

        as_dict = models.make_as_dict(POINT_MODEL, cls=dict)
        self.assertDictEqual({'x': 1, 'y': 2}, as_dict(Point(x=1, y=2)))

        as_dict = models.make_as_dict([POINT_MODEL.f.x])
        self.assertDictEqual({'x': 1}, as_dict(Point(x=1, y=2)))

    def test_as_namespace(self):
        as_namespace = models.make_as_namespace(POINT_MODEL)
        ns = as_namespace(x=1, y=2)
        self.assertEqual(1, ns.x)
        self.assertEqual(2, ns.y)

        refs = models.Refs()
        ns = as_namespace(x=refs.ref('x'), y=refs.ref('y'))
        with refs as context:
            context['x'] = 10
            context['y'] = 11
            self.assertEqual(10, ns.x)
            self.assertEqual(11, ns.y)


if __name__ == '__main__':
    unittest.main()
