import unittest

from garage import parts


class PartsTest(unittest.TestCase):

    def test_part_name(self):

        pn = parts.PartName('a.b.c', 'z')
        self.assertEqual('a.b.c:z', pn)
        self.assertEqual('a.b.c', pn.module_name)
        self.assertEqual('z', pn.name)

        pn = pn._rebase('d.e.f', 'x.y')
        self.assertEqual('d.e.f:x.y.z', pn)
        self.assertEqual('d.e.f', pn.module_name)
        self.assertEqual('x.y.z', pn.name)

        pattern = r'expect name not start with underscore: _x'
        with self.assertRaisesRegex(AssertionError, pattern):
            parts.PartName('a.b.c', '_x')

    def test_part_list(self):

        plist1 = parts.PartList('a.b.c', [
            ('x', parts.auto),
            ('y', 'Y'),
        ])

        plist2 = parts.PartList('d.e.f', [
            ('pl1', plist1),
            ('z', parts.auto),
        ])

        plist3 = parts.PartList('g.h.i', [
            ('pl1', plist1),
            ('pl2', plist2),
        ])

        self.assertEqual('a.b.c:x', plist1.x)
        self.assertEqual('a.b.c:Y', plist1.y)

        self.assertEqual('d.e.f:pl1.x', plist2.pl1.x)
        self.assertEqual('d.e.f:pl1.Y', plist2.pl1.y)
        self.assertEqual('d.e.f:z', plist2.z)

        self.assertEqual('g.h.i:pl1.x', plist3.pl1.x)
        self.assertEqual('g.h.i:pl1.Y', plist3.pl1.y)
        self.assertEqual('g.h.i:pl2.pl1.x', plist3.pl2.pl1.x)
        self.assertEqual('g.h.i:pl2.pl1.Y', plist3.pl2.pl1.y)


if __name__ == '__main__':
    unittest.main()
