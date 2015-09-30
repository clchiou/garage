import unittest

from garage import models
from garage.specs import base


POINT_MODEL = models.Model(
    'POINT_MODEL',
    models.Field('x'),
    models.Field('y'),
)


class ModelsTest(unittest.TestCase):

    def test_dict_builder(self):
        PointBuilder = base.make_dict_builder(POINT_MODEL, name='PointBuilder')

        p0 = PointBuilder().x(1).y(2)()
        self.assertDictEqual({'x': 1, 'y': 2}, p0)

        p1 = PointBuilder().x(3).y(4)()
        self.assertDictEqual({'x': 3, 'y': 4}, p1)

        p2 = PointBuilder(p0).x(5)()
        self.assertDictEqual({'x': 5, 'y': 2}, p2)

        with self.assertRaises(KeyError):
            PointBuilder().x(1)()

        self.assertIs(POINT_MODEL, PointBuilder._model)

    def test_namedtuple(self):
        Point = base.make_namedtuple(POINT_MODEL, name='Point')
        self.assertEqual((1, 2), Point(1, 2))


if __name__ == '__main__':
    unittest.main()
