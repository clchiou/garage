import unittest

from garage.okay import OKAY, NOT_OKAY


class OkayTest(unittest.TestCase):

    def test_okay(self):
        self.assertTrue(OKAY)
        self.assertFalse(NOT_OKAY)

        self.assertIs(~OKAY, NOT_OKAY)
        self.assertIs(OKAY, ~NOT_OKAY)

        self.assertIs(OKAY,     OKAY     & OKAY)
        self.assertIs(NOT_OKAY, NOT_OKAY & OKAY)
        self.assertIs(NOT_OKAY, OKAY     & NOT_OKAY)
        self.assertIs(NOT_OKAY, NOT_OKAY & NOT_OKAY)

        self.assertIs(OKAY,     OKAY     | OKAY)
        self.assertIs(OKAY,     NOT_OKAY | OKAY)
        self.assertIs(OKAY,     OKAY     | NOT_OKAY)
        self.assertIs(NOT_OKAY, NOT_OKAY | NOT_OKAY)

        self.assertIs(NOT_OKAY, OKAY     ^ OKAY)
        self.assertIs(OKAY,     NOT_OKAY ^ OKAY)
        self.assertIs(OKAY,     OKAY     ^ NOT_OKAY)
        self.assertIs(NOT_OKAY, NOT_OKAY ^ NOT_OKAY)


if __name__ == '__main__':
    unittest.main()
