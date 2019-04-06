import unittest

import copy
import dataclasses
import datetime
import enum
import json
import typing

from g1.messaging.wiredata import jsons


class TestEnum(enum.Enum):
    X = 1
    Y = 2


class TestError(Exception):

    def __eq__(self, other):
        return self.__class__ == other.__class__ and self.args == other.args


@dataclasses.dataclass
class SubType:
    y: int
    s: str


@dataclasses.dataclass
class TestType:
    n: type(None)
    x: int
    dt: datetime.datetime
    sub_obj: SubType
    en: TestEnum
    e: TestError
    t: typing.Tuple[int, str]
    l: typing.List[typing.Union[int, str]]
    u0: typing.Optional[SubType]
    u1: typing.Optional[SubType]
    default_x: int = 1


class JsonWireDataTest(unittest.TestCase):

    test_obj = TestType(
        n=None,
        x=1,
        dt=datetime.datetime(
            2000, 1, 2, 3, 4, 5, 6, tzinfo=datetime.timezone.utc
        ),
        sub_obj=SubType(y=2, s='hello world'),
        en=TestEnum.X,
        e=TestError(2, 'spam egg'),
        t=(1, 'some string'),
        l=[1, 2, 3, 'x', 'y', 'z'],
        u0=SubType(y=1, s='x'),
        u1=None,
    )

    raw_test_obj = {
        # type(None)
        'n':
        None,
        # int
        'x':
        1,
        # datetime
        'dt':
        '2000-01-02T03:04:05.000006+00:00',
        # SubType
        'sub_obj': {
            'y': 2,
            's': 'hello world',
        },
        # enum.Enum
        'en':
        'X',
        # TestError
        'e': {
            'TestError': [2, 'spam egg'],
        },
        # typing.Tuple[int, str]
        't': [1, 'some string'],
        # typing.List[typing.Union[int, str]]
        'l': [
            {
                'int': 1,
            },
            {
                'int': 2,
            },
            {
                'int': 3,
            },
            {
                'str': 'x',
            },
            {
                'str': 'y',
            },
            {
                'str': 'z',
            },
        ],
        # typing.Optional[SubType]
        'u0': {
            'y': 1,
            's': 'x',
        },
        # typing.Optional[SubType]
        'u1':
        None,
        # int
        'default_x':
        1,
    }

    raw_test_obj_no_default = copy.deepcopy(raw_test_obj)
    raw_test_obj_no_default.pop('default_x')

    # Some extra data that are ignored (forward compatibility).
    raw_test_obj_with_extra_data = copy.deepcopy(raw_test_obj)
    raw_test_obj_with_extra_data['some_extra_data'] = 'hello world'

    json_wire_data = jsons.JsonWireData()

    def test_end_to_end(self):
        self.assertEqual(
            self.json_wire_data.to_upper(
                TestType,
                self.json_wire_data.to_lower(self.test_obj),
            ),
            self.test_obj,
        )

    def test_to_lower(self):
        self.assertEqual(
            json.loads(self.json_wire_data.to_lower(self.test_obj)),
            self.raw_test_obj,
        )

    def test_to_upper(self):
        for raw_test_obj in (
            self.raw_test_obj,
            self.raw_test_obj_no_default,
            self.raw_test_obj_with_extra_data,
        ):
            with self.subTest(raw_test_obj):
                self.assertEqual(
                    self.json_wire_data.to_upper(
                        TestType,
                        json.dumps(raw_test_obj),
                    ),
                    self.test_obj,
                )

    def test_unwrap_optional_type(self):
        for type_ in (
            typing.Union[None, int, str],
            typing.Union[int, str],
        ):
            with self.subTest(type_):
                self.assertIsNone(jsons._unwrap_optional_type(type_))
        for type_ in (
            typing.Union[None, int],
            typing.Union[int, None],
        ):
            with self.subTest(type_):
                self.assertIs(jsons._unwrap_optional_type(type_), int)

    def test_match_recursive_type(self):

        for type_, value in (
            (int, 0),
            (typing.List[int], []),
            (typing.List[int], [1]),
            (typing.List[typing.List[int]], [[1], [2, 3]]),
            (typing.Tuple[int, str], (0, '')),
            (typing.Tuple[typing.Tuple[int]], ((0, ), )),
            (typing.Union[int, str], 0),
            (typing.Union[int, str], ''),
            (typing.Union[type(None), typing.Union[str, int]], 0),
        ):
            with self.subTest((type_, value)):
                self.assertTrue(jsons._match_recursive_type(type_, value))
        for type_, value in (
            (int, ''),
            (typing.List[int], [1, '']),
            (typing.List[typing.List[int]], [[1], [2, '']]),
            (typing.Tuple[int, str], [0, '']),
            (typing.Tuple[int, str], (0, )),
            (typing.Tuple[int, str], (0, 1)),
            (typing.Tuple[typing.Tuple[int]], (('', ), )),
            (typing.Union[int, str], ()),
            (typing.Union[type(None), typing.Union[str, int]], ()),
        ):
            with self.subTest((type_, value)):
                self.assertFalse(jsons._match_recursive_type(type_, value))

    def test_recursive_type(self):
        for type_, value, raw_value in (
            (typing.List[typing.List[int]], [], []),
            (typing.List[typing.List[int]], [[0], [1, 2]], [[0], [1, 2]]),
            (typing.Tuple[typing.Tuple[int]], ((0, ), ), ((0, ), )),
            (
                typing.Union[int, str],
                'x',
                {
                    'str': 'x',
                },
            ),
            (
                typing.Union[int, typing.List[int]],
                [],
                {
                    'typing.List[int]': [],
                },
            ),
        ):
            with self.subTest((type_, value)):
                self.assertEqual(
                    self.json_wire_data._encode_value(type_, value),
                    raw_value,
                )
                self.assertEqual(
                    self.json_wire_data._decode_raw_value(type_, raw_value),
                    value,
                )

        with self.assertRaisesRegex(TypeError, r'not iterable'):
            self.json_wire_data._encode_value(
                typing.List[typing.List[int]], [0]
            )

        with self.assertRaisesRegex(AssertionError, r'expect x == 1, not 2'):
            self.json_wire_data._encode_value(
                typing.Tuple[typing.Tuple[int]], ((0, 1), )
            )


if __name__ == '__main__':
    unittest.main()
