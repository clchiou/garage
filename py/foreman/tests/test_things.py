import unittest

from foreman import Label, Things


class ThingsTest(unittest.TestCase):

    def test_things(self):
        ax = Label.parse('//a:x')
        ay = Label.parse('//a:y')
        az = Label.parse('//a:z')
        bx = Label.parse('//b:x')
        by = Label.parse('//b:y')
        bz = Label.parse('//b:z')

        things = Things()

        self.assertFalse(ax in things)
        with self.assertRaises(KeyError):
            things[ax]
        self.assertIsNone(things.get(ax))

        things[ax] = 'ax'
        self.assertTrue(ax in things)
        self.assertEqual('ax', things[ax])
        self.assertEqual('ax', things.get(ax))

        self.assertEqual(['ax'], things.get_things(ax.path))
        self.assertEqual([], things.get_things(bx.path))

        things[ay] = 'ay'
        things[az] = 'az'
        # Reverse order.
        things[bz] = 'bz'
        things[by] = 'by'
        things[bx] = 'bx'

        self.assertEqual(['ax', 'ay', 'az'], things.get_things(ax.path))

        self.assertEqual([ax, ay, az, bz, by, bx], list(things))
        self.assertEqual(
            ['ax', 'ay', 'az', 'bz', 'by', 'bx'], list(things.values()))


if __name__ == '__main__':
    unittest.main()
