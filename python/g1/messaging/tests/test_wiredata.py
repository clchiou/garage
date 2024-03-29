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


class IntSubType(int):
    pass


@dataclasses.dataclass
class TestType:
    n: type(None)
    x: int
    b: bytes
    dt: datetime.datetime
    sub_obj: SubType
    en: TestEnum
    e: TestError
    t: typing.Tuple[int, str]
    l: typing.List[typing.Union[int, str]]
    s: typing.Set[str]
    d: typing.Dict[str, int]
    fs: typing.FrozenSet[str]
    u0: typing.Optional[SubType]
    u1: typing.Optional[SubType]
    int_sub_type: IntSubType
    default_x: int = 1


class JsonWireDataTest(unittest.TestCase):

    test_obj = TestType(
        n=None,
        x=1,
        b=b'hello world',
        dt=datetime.datetime(
            2000, 1, 2, 3, 4, 5, 6, tzinfo=datetime.timezone.utc
        ),
        sub_obj=SubType(y=2, s='hello world'),
        en=TestEnum.X,
        e=TestError(2, 'spam egg'),
        t=(1, 'some string'),
        l=[1, 2, 3, 'x', 'y', 'z'],
        s={'x'},
        d={
            'x': 1,
            'y': 2,
        },
        fs=frozenset(('x', )),
        u0=SubType(y=1, s='x'),
        u1=None,
        int_sub_type=IntSubType(1),
    )

    raw_test_obj = {
        # type(None)
        'n':
        None,
        # int
        'x':
        1,
        # bytes (BASE-64 encoded)
        'b':
        'aGVsbG8gd29ybGQ=',
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
        # typing.Set[str]
        's': ['x'],
        # typing.Dict[str, int]
        'd': {
            'x': 1,
            'y': 2,
        },
        # typing.FrozenSet[str]
        'fs': ['x'],
        # typing.Optional[SubType]
        'u0': {
            'y': 1,
            's': 'x',
        },
        # typing.Optional[SubType]
        'u1':
        None,
        'int_sub_type':
        1,
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

    def test_int_sub_type(self):
        actual = self.json_wire_data.to_upper(
            TestType,
            self.json_wire_data.to_lower(self.test_obj),
        )
        self.assertEqual(actual.int_sub_type, 1)
        self.assertIs(type(actual.int_sub_type), IntSubType)

    def test_match_recursive_type(self):

        for type_, value in (
            (int, 0),
            (typing.List[int], []),
            (typing.List[int], [1]),
            (typing.List[typing.List[int]], [[1], [2, 3]]),
            (typing.Tuple[int, str], (0, '')),
            (typing.Tuple[typing.Tuple[int]], ((0, ), )),
            (typing.Set[str], set()),
            (typing.Set[str], set(('x', ))),
            (typing.FrozenSet[str], frozenset()),
            (typing.FrozenSet[str], frozenset(('x', ))),
            (
                typing.Dict[str, int],
                {
                    'x': 1,
                    'y': 2,
                },
            ),
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
            (typing.Set[str], set((1, ))),
            (typing.FrozenSet[str], frozenset((1, ))),
            (
                typing.Dict[str, int],
                {
                    1: 'x',
                    2: 'y',
                },
            ),
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
                typing.Dict[str, typing.Tuple[int]],
                {
                    'x': (1, )
                },
                {
                    'x': (1, ),
                },
            ),
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

        with self.assertRaisesRegex(
            AssertionError,
            r'''expect subclass of <class 'str'>, not <class 'int'>''',
        ):
            self.json_wire_data._encode_value(typing.Dict[int, str], {1: 'x'})


if __name__ == '__main__':
    unittest.main()
