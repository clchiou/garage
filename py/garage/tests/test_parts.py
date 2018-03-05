import unittest

import functools
from collections import defaultdict

from tests.availability import startup_available

if startup_available:
    from garage import parts

    PLIST = parts.PartList('a.b.c', [
        ('sub_part_1', parts.AUTO),
        ('sub_part_2', parts.AUTO),
        ('final_part', parts.AUTO),
        ('some_part', parts.AUTO),
    ])

    def make_sub_part_1() -> PLIST.sub_part_1:
        return 'part from make_sub_part_1'

    def make_sub_part_1_another() -> PLIST.sub_part_1:
        return 'part from make_sub_part_1_another'

    def make_sub_part_1_yet_another() -> PLIST.sub_part_1:
        return 'part from make_sub_part_1_yet_another'

    def make_sub_part_2() -> PLIST.sub_part_2:
        return 'part from make_sub_part_2'

    def make_all_sub_parts() -> (PLIST.sub_part_1, PLIST.sub_part_2):
        return (
            'part 1 from make_all_sub_parts',
            'part 2 from make_all_sub_parts',
        )

    def make_final_part(
            sub_part_1: PLIST.sub_part_1,
            sub_part_2: [PLIST.sub_part_2],
            ) -> PLIST.final_part:
        return 'part from make_final_part'


@unittest.skipUnless(startup_available, 'startup unavailable')
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
            ('x', parts.AUTO),
            ('y', 'Y'),
        ])

        plist2 = parts.PartList('d.e.f', [
            ('pl1', plist1),
            ('z', parts.AUTO),
        ])

        plist3 = parts.PartList('g.h.i', [
            ('pl1', plist1),
            ('pl2', plist2),
        ])

        plist4 = parts.PartList('j.k.l', [
            ('pl3', plist3),
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

        self.assertEqual('j.k.l:pl3.pl2.pl1.x', plist4.pl3.pl2.pl1.x)
        self.assertEqual('j.k.l:pl3.pl2.pl1.Y', plist4.pl3.pl2.pl1.y)

    def test_define_maker_on_wrapper(self):

        plist = parts.PartList('foo', [('x', parts.AUTO), ('y', parts.AUTO)])

        def func(x: plist.x, arg) -> plist.y:
            pass

        f1 = functools.partial(func, arg=None)

        @functools.wraps(func)
        def f2(x):
            pass

        def f3(xs: [plist.x]) -> plist.y:
            pass

        maker_table = defaultdict(dict)
        parts._define_maker(maker_table, func)
        parts._define_maker(maker_table, f1)
        parts._define_maker(maker_table, f2)
        parts._define_maker(maker_table, f3)
        self.assertEqual(
            {
                plist.y: {
                    func: (parts.InputSpec('x', plist.x, False),),
                    f1: (parts.InputSpec('x', plist.x, False),),
                    f2: (parts.InputSpec('x', plist.x, False),),
                    f3: (parts.InputSpec('xs', plist.x, True),),
                },
            },
            maker_table,
        )

    def test_find_sources(self):

        maker_table = defaultdict(dict)
        parts._define_maker(maker_table, make_sub_part_1)
        parts._define_maker(maker_table, make_sub_part_2)
        parts._define_maker(maker_table, make_final_part)

        self.assert_sources_equal(
            [
                (make_final_part, None),
                (make_sub_part_1, None),
                (make_sub_part_2, None),
            ],
            parts.find_sources(
                [PLIST.final_part],
                {},
                maker_table,
                {},
            ),
        )

        pattern = r'expect part a.b.c:some_part from caller'
        with self.assertRaisesRegex(AssertionError, pattern):
            list(parts.find_sources(
                [PLIST.some_part],
                {},
                maker_table,
                {},
            ))

        maker_table = defaultdict(dict)
        parts._define_maker(maker_table, make_all_sub_parts)
        parts._define_maker(maker_table, make_final_part)

        self.assert_sources_equal(
            [
                (make_all_sub_parts, None),
                (make_final_part, None),
            ],
            parts.find_sources(
                [PLIST.final_part],
                {},
                maker_table,
                {},
            ),
        )

        maker_table = defaultdict(dict)
        parts._define_maker(maker_table, make_sub_part_2)
        parts._define_maker(maker_table, make_all_sub_parts)

        self.assert_sources_equal(
            [
                (None, (PLIST.sub_part_2, 'world')),
                (make_sub_part_2, None),
                (make_all_sub_parts, None),
            ],
            parts.find_sources(
                [[PLIST.sub_part_2]],  # Test [x] annotation.
                {PLIST.sub_part_2: 'world'},
                maker_table,
                {},
            ),
        )

    def test_find_sources_with_input_parts(self):

        maker_table = defaultdict(dict)
        parts._define_maker(maker_table, make_final_part)

        self.assert_sources_equal(
            [
                (make_final_part, None),
                (None, (PLIST.sub_part_1, 'hello')),
                (None, (PLIST.sub_part_2, 'world')),
            ],
            parts.find_sources(
                [PLIST.final_part],
                {PLIST.sub_part_1: 'hello', PLIST.sub_part_2: 'world'},
                maker_table,
                {},
            ),
        )

        pattern = r'expect part a.b.c:sub_part_2 from caller'
        with self.assertRaisesRegex(AssertionError, pattern):
            list(parts.find_sources(
                [PLIST.final_part],
                {PLIST.sub_part_1: 'hello'},
                maker_table,
                {},
            ))

        maker_table = defaultdict(dict)
        parts._define_maker(maker_table, make_final_part)
        parts._define_maker(maker_table, make_sub_part_1)

        pattern = r'expect part a.b.c:sub_part_1 by maker, not from caller'
        with self.assertRaisesRegex(AssertionError, pattern):
            list(parts.find_sources(
                [PLIST.final_part],
                {PLIST.sub_part_1: 'hello', PLIST.sub_part_2: 'world'},
                maker_table,
                {},
            ))

    def test_find_sources_with_selected_makers(self):

        maker_table = defaultdict(dict)
        parts._define_maker(maker_table, make_sub_part_1)
        parts._define_maker(maker_table, make_sub_part_1_another)
        parts._define_maker(maker_table, make_sub_part_2)
        parts._define_maker(maker_table, make_final_part)

        self.assert_sources_equal(
            [
                (make_final_part, None),
                (make_sub_part_1_another, None),
                (make_sub_part_2, None),
            ],
            parts.find_sources(
                [PLIST.final_part],
                {},
                maker_table,
                {PLIST.sub_part_1: [make_sub_part_1_another]},
            ),
        )

        self.assert_sources_equal(
            [
                (make_final_part, None),
                (make_sub_part_1, None),
                (make_sub_part_1_another, None),
                (make_sub_part_2, None),
            ],
            parts.find_sources(
                [PLIST.final_part],
                {},
                maker_table,
                {PLIST.sub_part_1: all},
            ),
        )

        pattern = r'expect caller to select maker\(s\) for a.b.c:sub_part_1'
        with self.assertRaisesRegex(AssertionError, pattern):
            list(parts.find_sources(
                [PLIST.final_part],
                {},
                maker_table,
                {},
            ))

        pattern = (
            r'expect maker to be registered: '
            r'<function make_sub_part_1_yet_another at.*>'
        )
        with self.assertRaisesRegex(AssertionError, pattern):
            list(parts.find_sources(
                [PLIST.final_part],
                {},
                maker_table,
                {PLIST.sub_part_1: [make_sub_part_1_yet_another]},
            ))

    def assert_sources_equal(self, expect, actual):
        self.assertEqual(sorted(expect, key=str), sorted(actual, key=str))

    def test_assemble(self):

        maker_table = defaultdict(dict)
        parts._define_maker(maker_table, make_sub_part_1)
        parts._define_maker(maker_table, make_sub_part_2)
        parts._define_maker(maker_table, make_final_part)

        self.assertEqual(
            {
                PLIST.sub_part_1: 'part from make_sub_part_1',
                PLIST.sub_part_2: 'part from make_sub_part_2',
                PLIST.final_part: 'part from make_final_part',
            },
            parts._assemble(
                maker_table,
                [PLIST.final_part],
                {},
                {},
            ),
        )

        maker_table = defaultdict(dict)
        parts._define_maker(maker_table, make_all_sub_parts)
        parts._define_maker(maker_table, make_final_part)

        self.assertEqual(
            {
                PLIST.sub_part_1: 'part 1 from make_all_sub_parts',
                PLIST.sub_part_2: 'part 2 from make_all_sub_parts',
                PLIST.final_part: 'part from make_final_part',
            },
            parts._assemble(
                maker_table,
                [PLIST.final_part],
                {},
                {},
            ),
        )

        maker_table = defaultdict(dict)
        parts._define_maker(maker_table, make_sub_part_1)
        parts._define_maker(maker_table, make_final_part)

        self.assertEqual(
            {
                PLIST.sub_part_1: 'part from make_sub_part_1',
                PLIST.sub_part_2: 'part from input',
                PLIST.final_part: 'part from make_final_part',
            },
            parts._assemble(
                maker_table,
                [PLIST.final_part],
                {PLIST.sub_part_2: 'part from input'},
                {},
            ),
        )


if __name__ == '__main__':
    unittest.main()
