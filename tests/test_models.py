import unittest

from garage import models


class ModelsTest(unittest.TestCase):

    def test_models(self):
        PointModel = models.Model(
            'Point',
            models.Field('x'),
            models.Field('y'),
        )

        PointBuilder = PointModel.make_builder()
        point = PointBuilder().x(1)(y=2)
        self.assertDictEqual({'x': 1, 'y': 2}, point)

        Point = PointModel.make_namedtuple()
        PointBuilder = PointModel.make_builder(build=Point)
        point = PointBuilder().x(1).y(2)()
        self.assertEqual(1, point.x)
        self.assertEqual(2, point.y)


if __name__ == '__main__':
    unittest.main()
