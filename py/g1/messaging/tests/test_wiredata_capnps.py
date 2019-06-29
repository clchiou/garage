import unittest

import dataclasses
import datetime
import enum
import typing
from pathlib import Path

import capnp

from g1.messaging.wiredata import capnps

try:
    from g1.devtools import tests
except ImportError:
    tests = None

# These types have to match those defined in `testdata/test-1.capnp`.


class SomeError(Exception):

    def __eq__(self, other):
        return type(self) is type(other) and self.args == other.args


@dataclasses.dataclass
class NestedEmptyStruct:
    pass


class SomeEnum(enum.Enum):
    ENUM_MEMBER_0 = 0
    ENUM_MEMBER_1 = 1


@dataclasses.dataclass
class UnionField:
    bool_field: typing.Optional[bool]
    bytes_field: typing.Optional[bytes]


@dataclasses.dataclass
class UnionVoidField:
    union_void_field: typing.Optional[type(None)]
    union_bytes_field: typing.Optional[bytes]


@dataclasses.dataclass
class SomeStruct:

    __module__ = 'g1.messaging.tests.test_1'

    void_field: capnp.VoidType
    int_field: int
    int_with_default: int
    str_field: str
    int_timestamp: datetime.datetime
    float_timestamp: datetime.datetime
    enum_field: SomeEnum
    struct_field: NestedEmptyStruct
    error_field: SomeError
    union_int_field: typing.Optional[int]
    union_error_field: typing.Optional[SomeError]
    union_field: UnionField
    int_list_field: typing.List[int]
    tuple_field: typing.Tuple[int, bool]
    none_field: type(None)
    union_void_field: UnionVoidField
    str_with_default: str


@unittest.skipUnless(tests, 'g1.tests unavailable')
@unittest.skipUnless(
    tests and tests.check_program(['capnp', '--version']),
    'capnp unavailable',
)
class CapnpWireDataTest(unittest.TestCase):

    TESTDATA_PATH = Path(__file__).parent / 'testdata'

    @classmethod
    def compile(cls, path):
        path = str(cls.TESTDATA_PATH / path)
        return tests.check_output(['capnp', 'compile', '-o-', path])

    @classmethod
    def setUpClass(cls):
        cls.loader = capnp.SchemaLoader()
        cls.loader.load_once(cls.compile('test-1.capnp'))
        cls.schema = cls.loader.struct_schemas[
            'g1.messaging.tests.test_1:SomeStruct']
        cls.wire_data = capnps.CapnpWireData(cls.loader)
        cls.packed_wire_data = capnps.CapnpPackedWireData(cls.loader)

    def test_wiredata(self):

        dt = datetime.datetime(2000, 1, 2, 3, 4, 5, 6, datetime.timezone.utc)
        self.assertNotEqual(dt.microsecond, 0)

        msg = capnp.MessageBuilder()
        builder = msg.init_root(self.schema)
        builder['voidField'] = capnp.VOID
        builder['intField'] = 13
        builder['strField'] = 'hello world'
        builder['intTimestamp'] = int(dt.timestamp())
        builder['floatTimestamp'] = dt.timestamp()
        builder['enumField'] = SomeEnum.ENUM_MEMBER_1
        builder.init('structField')
        b = builder.init('errorField')
        b['code'] = 7
        b['reason'] = 'some error'
        builder['unionErrorField'] = capnp.VOID
        builder.init('unionField')['bytesField'] = b'hello world'
        b = builder.init('intListField', 3)
        b[0] = 2
        b[1] = 3
        b[2] = 5
        b = builder.init('tupleField')
        b['intGroupField'] = 99
        b['boolGroupField'] = True
        builder['noneField'] = capnp.VOID
        builder.init('unionVoidField')['unionBytesField'] = b''
        builder['strWithDefault'] = 'spam egg'

        obj = SomeStruct(
            void_field=capnp.VOID,
            int_field=13,
            int_with_default=42,
            str_field='hello world',
            int_timestamp=dt.replace(microsecond=0),
            float_timestamp=dt,
            enum_field=SomeEnum.ENUM_MEMBER_1,
            struct_field=NestedEmptyStruct(),
            error_field=SomeError(7, 'some error'),
            union_int_field=None,
            union_error_field=SomeError(),
            union_field=UnionField(
                bool_field=None,
                bytes_field=b'hello world',
            ),
            int_list_field=[2, 3, 5],
            tuple_field=(99, True),
            none_field=None,
            union_void_field=UnionVoidField(
                union_void_field=None,
                union_bytes_field=b'',
            ),
            str_with_default='spam egg',
        )

        for to_testdata, wd in (
            (msg.to_message_bytes, self.wire_data),
            (msg.to_packed_message_bytes, self.packed_wire_data),
        ):
            with self.subTest((to_testdata, wd)):
                testdata = to_testdata()
                self.assertEqual(wd.to_lower(obj), testdata)
                self.assertEqual(wd.to_upper(SomeStruct, testdata), obj)

    def test_zero(self):

        dt = datetime.datetime(1970, 1, 1, 0, 0, 0, 0, datetime.timezone.utc)

        msg = capnp.MessageBuilder()
        msg.init_root(self.schema)

        obj1 = SomeStruct(
            void_field=capnp.VOID,
            int_field=0,
            int_with_default=42,
            str_field=None,
            int_timestamp=dt,
            float_timestamp=dt,
            enum_field=SomeEnum.ENUM_MEMBER_0,
            struct_field=None,
            error_field=None,
            union_int_field=0,
            union_error_field=None,
            union_field=UnionField(
                bool_field=False,
                bytes_field=None,
            ),
            int_list_field=None,
            tuple_field=(0, False),
            none_field=None,
            union_void_field=UnionVoidField(
                union_void_field=None,
                union_bytes_field=None,
            ),
            str_with_default=None,
        )
        obj2 = dataclasses.replace(obj1, str_with_default='default message')

        for to_testdata, wd in (
            (msg.to_message_bytes, self.wire_data),
            (msg.to_packed_message_bytes, self.packed_wire_data),
        ):
            with self.subTest((to_testdata, wd)):
                testdata = to_testdata()
                self.assertEqual(wd.to_lower(obj1), testdata)
                self.assertEqual(wd.to_upper(SomeStruct, testdata), obj2)


if __name__ == '__main__':
    unittest.main()
