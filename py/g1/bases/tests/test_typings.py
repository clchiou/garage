import unittest

import typing

from g1.bases import typings


class TypingsTest(unittest.TestCase):

    def test_match_optional_type(self):
        for type_ in (
            typing.Union[None, int, str],
            typing.Union[int, str],
        ):
            with self.subTest(type_):
                self.assertIsNone(typings.match_optional_type(type_))
        for type_ in (
            typing.Union[None, int],
            typing.Union[int, None],
        ):
            with self.subTest(type_):
                self.assertIs(typings.match_optional_type(type_), int)


if __name__ == '__main__':
    unittest.main()
