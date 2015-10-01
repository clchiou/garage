import unittest

from garage import models
from garage.specs import base


POINT_MODEL = models.Model(
    'POINT_MODEL',
    models.Field('x'),
    models.Field('y'),
)


class BaseTest(unittest.TestCase):

    def test_as_dict(self):
        Point = base.make_namedtuple(POINT_MODEL, name='Point')

        as_dict = base.make_as_dict(POINT_MODEL, cls=dict)
        self.assertDictEqual({'x': 1, 'y': 2}, as_dict(Point(1, 2)))

        as_dict = base.make_as_dict([POINT_MODEL.f.x])
        self.assertDictEqual({'x': 1}, as_dict(Point(1, 2)))

    def test_namedtuple(self):
        Point = base.make_namedtuple(POINT_MODEL, name='Point')
        self.assertEqual((1, 2), Point(1, 2))


if __name__ == '__main__':
    unittest.main()
