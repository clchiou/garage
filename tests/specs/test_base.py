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
        Point = base.make_as_namespace(POINT_MODEL)

        as_dict = base.make_as_dict(POINT_MODEL, cls=dict)
        self.assertDictEqual({'x': 1, 'y': 2}, as_dict(Point(x=1, y=2)))

        as_dict = base.make_as_dict([POINT_MODEL.f.x])
        self.assertDictEqual({'x': 1}, as_dict(Point(x=1, y=2)))

    def test_as_namespace(self):
        as_namespace = base.make_as_namespace(POINT_MODEL)
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
