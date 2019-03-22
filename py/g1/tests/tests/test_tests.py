import unittest

import enum
import subprocess
from pathlib import Path

from g1 import tests


class TestEnum(enum.Enum):
    P = 1
    Q = 2


class DelTest(unittest.TestCase):

    def test_resurrecting_self(self):

        class Resurrect:

            def __del__(self):
                Resurrect.dont_recycle_me = self

        with self.assertRaisesRegex(AssertionError, r'is not None'):
            tests.assert_del_not_resurrecting(self, Resurrect)


@unittest.skipUnless(tests.is_gcc_available(), 'gcc unavailable')
class CFixtureTest(unittest.TestCase, tests.CFixture):

    HEADERS = (Path(__file__).absolute().parent / 'testdata' / 'test.h', )

    def test_run_c_code(self):
        stdout = self.run_c_code(
            r'''
            #include <stdio.h>
            int main() {
                printf("Hello, world!\n");
                return 0;
            }
            '''
        )
        self.assertEqual(stdout, b'Hello, world!\n')

    def test_assert_c_expr(self):
        self.assert_c_expr('1')  # This should not raise.
        with self.assertRaises(subprocess.CalledProcessError):
            self.assert_c_expr('0')

    def test_get_c_vars(self):

        self.assertEqual(self.get_c_vars({}), {})

        self.assertEqual(
            self.get_c_vars({
                'x': int,
                's': str,
            }),
            {
                'x': 1,
                's': 'Hello, world!\n',
            },
        )

    def test_get_enum_members(self):
        self.assertEqual(self.get_enum_members(TestEnum), TestEnum.__members__)


class SpawnTest(unittest.TestCase):

    def test_spawn(self):
        self.assertEqual(tests.spawn(lambda x: x + 1, 1).result(), 2)


if __name__ == '__main__':
    unittest.main()
