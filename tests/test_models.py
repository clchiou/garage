import unittest

from argparse import Namespace

from garage import models


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
            context['p'] = p = Namespace()
            self.assertEqual(p, ref.deref())

        ref = refs.ref('p.x')
        with refs as context:
            context['p'] = p = Namespace()
            p.x = 1
            self.assertEqual(1, ref.deref())

        ref = refs.ref('q.y.y')
        with refs as context:
            context['q'] = q = Namespace()
            q.y = Namespace()
            q.y.y = 2
            self.assertEqual(2, ref.deref())

        with self.assertRaises(AttributeError):
            ref.deref()

        with refs as context:
            context['p'] = Namespace()
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


if __name__ == '__main__':
    unittest.main()
