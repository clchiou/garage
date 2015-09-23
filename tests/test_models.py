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

        ref = models.Ref('p')
        self.assertEqual(p, ref.deref({'p': p}))

        ref = models.Ref('p.x')
        self.assertEqual(1, ref.deref({'p': p}))

        ref = models.Ref('q.y.y')
        self.assertEqual(2, ref.deref({'q': q}))

        with self.assertRaises(AttributeError):
            ref.deref({})

        with self.assertRaises(AttributeError):
            models.Ref('p.z').deref({'p': p})


if __name__ == '__main__':
    unittest.main()
