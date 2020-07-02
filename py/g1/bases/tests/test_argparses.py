import unittest

import argparse
import datetime
import enum

from g1.bases import argparses


class TestEnum(enum.Enum):

    FOO_BAR = enum.auto()
    SPAM_EGG = enum.auto()


class ArgparsesTest(unittest.TestCase):

    def test_append_const_and_value_action(self):
        parser = argparse.ArgumentParser()
        parser.add_argument(
            '--value',
            action=argparses.AppendConstAndValueAction,
            dest='target',
            const='from-value',
        )
        parser.add_argument(
            '--many',
            action=argparses.AppendConstAndValueAction,
            dest='target',
            const='from-many',
            nargs='*',
        )
        args = parser.parse_args(
            '--value 1 '
            '--many '
            '--value 2 '
            '--many 3 4'.split()
        )
        self.assertEqual(
            args.target,
            [
                ('from-value', '1'),
                ('from-many', []),
                ('from-value', '2'),
                ('from-many', ['3', '4']),
            ],
        )

    def test_store_bool_action(self):
        parser = argparse.ArgumentParser()

        action = parser.add_argument(
            '--default',
            action=argparses.StoreBoolAction,
            default=True,
        )
        self.assertIs(action.default, True)
        self.assertIs(action.type, None)
        self.assertFalse(action.required)

        action = parser.add_argument(
            '--required',
            action=argparses.StoreBoolAction,
            required=True,
        )
        self.assertIs(action.default, None)
        self.assertIs(action.type, None)
        self.assertTrue(action.required)

        # Weird but legal combination; should we outlaw this?
        action = parser.add_argument(
            '--default-and-required',
            action=argparses.StoreBoolAction,
            default=True,
            required=True,
        )
        self.assertIs(action.default, True)
        self.assertIs(action.type, None)
        self.assertTrue(action.required)

        action = parser.add_argument(
            'positional',
            action=argparses.StoreBoolAction,
        )
        self.assertIs(action.default, None)
        self.assertIs(action.type, None)
        self.assertTrue(action.required)

        args = parser.parse_args(
            '--required true '
            '--default-and-required true '
            'true'.split()
        )
        self.assertIs(args.default, True)
        self.assertIs(args.required, True)
        self.assertIs(args.default_and_required, True)
        self.assertIs(args.positional, True)

        args = parser.parse_args(
            '--default false '
            '--required false '
            '--default-and-required false '
            'false'.split()
        )
        self.assertIs(args.default, False)
        self.assertIs(args.required, False)
        self.assertIs(args.default_and_required, False)
        self.assertIs(args.positional, False)

    def test_store_enum_action(self):
        parser = argparse.ArgumentParser()

        action = parser.add_argument(
            '--default',
            action=argparses.StoreEnumAction,
            default=TestEnum.FOO_BAR,
        )
        self.assertIs(action.default, TestEnum.FOO_BAR)
        self.assertIs(action.type, None)
        self.assertFalse(action.required)

        action = parser.add_argument(
            '--required',
            action=argparses.StoreEnumAction,
            type=TestEnum,
            required=True,
        )
        self.assertIs(action.default, None)
        self.assertIs(action.type, None)
        self.assertTrue(action.required)

        # Weird but legal combination; should we outlaw this?
        action = parser.add_argument(
            '--default-and-required',
            action=argparses.StoreEnumAction,
            default=TestEnum.FOO_BAR,
            required=True,
        )
        self.assertIs(action.default, TestEnum.FOO_BAR)
        self.assertIs(action.type, None)
        self.assertTrue(action.required)

        action = parser.add_argument(
            'positional',
            action=argparses.StoreEnumAction,
            type=TestEnum,
        )
        self.assertIs(action.default, None)
        self.assertIs(action.type, None)
        self.assertTrue(action.required)

        args = parser.parse_args(
            '--required foo-bar '
            '--default-and-required foo-bar '
            'foo-bar'.split()
        )
        self.assertIs(args.default, TestEnum.FOO_BAR)
        self.assertIs(args.required, TestEnum.FOO_BAR)
        self.assertIs(args.default_and_required, TestEnum.FOO_BAR)
        self.assertIs(args.positional, TestEnum.FOO_BAR)

        args = parser.parse_args(
            '--default spam-egg '
            '--required spam-egg '
            '--default-and-required spam-egg '
            'spam-egg'.split()
        )
        self.assertIs(args.default, TestEnum.SPAM_EGG)
        self.assertIs(args.required, TestEnum.SPAM_EGG)
        self.assertIs(args.default_and_required, TestEnum.SPAM_EGG)
        self.assertIs(args.positional, TestEnum.SPAM_EGG)

    def test_parse_name_value_pair(self):
        self.assertEqual(argparses.parse_name_value_pair('x=1'), ('x', 1))
        self.assertEqual(
            argparses.parse_name_value_pair(
                'x=1',
                parsers=(TestEnum.__getitem__, ),
            ),
            ('x', 1),
        )
        self.assertEqual(
            argparses.parse_name_value_pair(
                'x=FOO_BAR',
                parsers=(TestEnum.__getitem__, ),
            ),
            ('x', TestEnum.FOO_BAR),
        )

    def test_parse_value(self):
        self.assertEqual(argparses._parse_value('true'), True)
        self.assertEqual(argparses._parse_value('false'), False)
        self.assertEqual(argparses._parse_value('not_true'), 'not_true')
        self.assertEqual(argparses._parse_value('{"x": 1}'), {'x': 1})

    def test_parse_timedelta(self):
        with self.assertRaisesRegex(AssertionError, r'expect non-empty'):
            argparses.parse_timedelta('')
        with self.assertRaisesRegex(AssertionError, r'expect non-None value'):
            argparses.parse_timedelta('   ')
        with self.assertRaisesRegex(AssertionError, r'expect non-None value'):
            argparses.parse_timedelta('-1d')
        with self.assertRaisesRegex(AssertionError, r'expect non-None value'):
            argparses.parse_timedelta('99')
        with self.assertRaisesRegex(AssertionError, r'expect non-None value'):
            argparses.parse_timedelta('1d  1s')
        with self.assertRaisesRegex(AssertionError, r'expect non-None value'):
            argparses.parse_timedelta('1s1m')
        self.assertEqual(
            datetime.timedelta(seconds=1),
            argparses.parse_timedelta('1s'),
        )
        self.assertEqual(
            datetime.timedelta(hours=2, seconds=3),
            argparses.parse_timedelta('2h3s'),
        )
        self.assertEqual(
            datetime.timedelta(days=1111, hours=22, minutes=33, seconds=44),
            argparses.parse_timedelta('1111d22h33m44s')
        )

    def test_no_decoration(self):

        def main():
            pass

        with self.assertRaisesRegex(
            AssertionError, r'expect exactly one left:'
        ):
            argparses.make_argument_parser(main)

    def test_mismatch_end(self):

        @argparses.argument_parser()
        @argparses.end
        def main_1():
            pass

        with self.assertRaisesRegex(
            AssertionError, r'expect exactly one left:'
        ):
            argparses.make_argument_parser(main_1)

        @argparses.argument_parser()
        @argparses.begin_argument('-x')
        def main_2():
            pass

        with self.assertRaisesRegex(
            AssertionError, r'expect exactly one left:'
        ):
            argparses.make_argument_parser(main_2)

    def test_simple_args(self):

        @argparses.argument_parser()
        @argparses.argument('x')
        @argparses.argument('y')
        def main():
            pass

        parser = argparses.make_argument_parser(main)
        self.assertEqual(
            vars(parser.parse_args(['1', '2'])),
            {
                'x': '1',
                'y': '2',
            },
        )

    def test_apply(self):

        @argparses.argument_parser()
        @argparses.argument('x')
        @argparses.begin_argument('y')
        @argparses.apply(lambda action: setattr(action, 'dest', 'z'))
        @argparses.end
        def main():
            pass

        parser = argparses.make_argument_parser(main)
        self.assertEqual(
            vars(parser.parse_args(['1', '2'])),
            {
                'x': '1',
                'z': '2',
            },
        )

    def test_subcmds(self):

        @argparses.argument_parser()
        @argparses.argument('-x')
        @argparses.begin_subparsers_for_subcmds(dest='cmd')
        @argparses.begin_parser('cmd_a')
        @argparses.argument('a')
        @argparses.end
        @argparses.begin_parser('cmd_b')
        @argparses.argument('b')
        @argparses.end
        @argparses.end
        def main():
            pass

        parser = argparses.make_argument_parser(main)
        self.assertEqual(
            vars(parser.parse_args(['-x', '1', 'cmd_a', '2'])),
            {
                'cmd': 'cmd_a',
                'a': '2',
                'x': '1',
            },
        )
        self.assertEqual(
            vars(parser.parse_args(['cmd_b', '1'])),
            {
                'cmd': 'cmd_b',
                'b': '1',
                'x': None,
            },
        )


if __name__ == '__main__':
    unittest.main()
