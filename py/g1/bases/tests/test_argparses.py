import unittest

import argparse
import datetime
import enum

from g1.bases import argparses


class TestEnum(enum.Enum):

    FOO_BAR = enum.auto()
    SPAM_EGG = enum.auto()


class ArgparsesTest(unittest.TestCase):

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


if __name__ == '__main__':
    unittest.main()
