import unittest

from garage import models


PointModel = models.Model(
    'Point',
    models.Field('x'),
    models.Field('y'),
)


class ModelsTest(unittest.TestCase):

    def test_models(self):
        PointBuilder = PointModel.make_builder()
        point = PointBuilder().x(1)(y=2)
        self.assertDictEqual({'x': 1, 'y': 2}, point)

        Point = PointModel.make_namedtuple()
        PointBuilder = PointModel.make_builder(build=Point)
        point = PointBuilder().x(1).y(2)()
        self.assertEqual(1, point.x)
        self.assertEqual(2, point.y)

    def test_ref(self):
        Point = PointModel.make_namedtuple()
        p = Point(1, 2)
        q = Point(3, p)

        refs = models.Refs()

        ref = refs.ref('p')
        with refs as context:
            context['p'] = p
            self.assertEqual(p, ref.deref())

        ref = refs.ref('p.x')
        with refs as context:
            context['p'] = p
            self.assertEqual(1, ref.deref())

        ref = refs.ref('q.y.y')
        with refs as context:
            context['q'] = q
            self.assertEqual(2, ref.deref())

        with self.assertRaises(AttributeError):
            ref.deref()

        with refs as context:
            context['p'] = p
            with self.assertRaises(AttributeError):
                refs.ref('p.z').deref()

    def test_deref(self):
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


if __name__ == '__main__':
    unittest.main()
