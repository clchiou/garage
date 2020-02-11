import unittest

import dataclasses
import datetime
import enum
import typing
from pathlib import Path

try:
    from g1.devtools import tests
except ImportError:
    tests = None

import capnp
from capnp import objects

NoneType = type(None)


@dataclasses.dataclass(frozen=True)
class TestSimpleStruct:

    void_field: capnp.VoidType

    bool_field: bool

    int8_field: int
    int16_field: int
    int32_field: int
    int64_field: int

    uint8_field: int
    uint16_field: int
    uint32_field: int
    uint64_field: int

    float32_field: float
    float64_field: float

    text_field_1: str
    text_field_2: str
    data_field_1: bytes
    data_field_2: bytes

    int_list_field: typing.List[int]
    text_list_field: typing.List[str]

    class TestEnum(enum.Enum):
        member0 = 0
        member1 = 1
        member2 = 2

    enum_field: TestEnum

    datetime_int_field: datetime.datetime
    datetime_float_field: datetime.datetime

    nested_list: typing.List[typing.List[typing.List[typing.Tuple[int]]]]


@dataclasses.dataclass(frozen=True)
class TestInvalidDatetimeIntStruct:
    datetime_field: datetime.datetime


@dataclasses.dataclass(frozen=True)
class TestInvalidDatetimeFloatStruct:
    datetime_field: datetime.datetime


@dataclasses.dataclass(frozen=True)
class TestPointerStruct:

    @dataclasses.dataclass(frozen=True)
    class EmptyStruct:
        pass

    @dataclasses.dataclass(frozen=True)
    class GroupField:
        group_int_field: int

    class TestException(Exception):

        def __eq__(self, other):
            return type(self) is type(other) and self.args == other.args

    class TestException2(TestException):
        pass

    group_field: GroupField
    tuple_field_1: typing.Tuple[int]
    tuple_field_2: typing.Tuple[int]
    exception_field_1: TestException
    exception_field_2: TestException2
    struct_field: EmptyStruct


@dataclasses.dataclass(frozen=True)
class TestUnionStruct:

    @dataclasses.dataclass(frozen=True)
    class U0:
        m0: typing.Optional[NoneType]
        m1: typing.Optional[str]

    @dataclasses.dataclass(frozen=True)
    class U1:
        m2: typing.Optional[int]
        m3: typing.Optional[NoneType]
        m4: typing.Optional[bytes]

    @dataclasses.dataclass(frozen=True)
    class U2:
        m5: typing.Optional[NoneType]
        m6: typing.Optional[TestPointerStruct.EmptyStruct]

    u0: U0
    u1: U1
    u2: U2
    m7: typing.Optional[NoneType]
    m8: typing.Optional[bool]


@dataclasses.dataclass(frozen=True)
class TestNestedUnionStruct:

    @dataclasses.dataclass(frozen=True)
    class U0:
        m0: typing.Optional[bool]
        m1: typing.Optional[int]
        m2: typing.Optional[NoneType]

    @dataclasses.dataclass(frozen=True)
    class U1:
        m3: typing.Optional[str]
        m4: typing.Optional[bytes]

    u0: typing.Optional[U0]
    u1: typing.Optional[U1]


class RecursiveStruct:
    pass


RecursiveStruct.__annotations__ = {'struct_field': RecursiveStruct}
dataclasses.dataclass(frozen=True)(RecursiveStruct)


class IntSubType(int):
    pass


@dataclasses.dataclass(frozen=True)
class TestSubType:

    @dataclasses.dataclass(frozen=True)
    class IntSubTypeUnion:
        int_sub_type: typing.Optional[IntSubType]
        irrelevant: typing.Optional[NoneType]

    int_sub_type: IntSubType
    int_sub_type_union: IntSubTypeUnion


@unittest.skipUnless(tests, 'g1.tests unavailable')
@unittest.skipUnless(
    tests and tests.check_program(['capnp', '--version']),
    'capnp unavailable',
)
class ObjectsTest(unittest.TestCase):

    TESTDATA_PATH = Path(__file__).parent / 'testdata'

    @classmethod
    def compile(cls, path):
        path = str(cls.TESTDATA_PATH / path)
        return tests.check_output(['capnp', 'compile', '-o-', path])

    @classmethod
    def setUpClass(cls):
        cls.loader = capnp.SchemaLoader()
        cls.loader.load_once(cls.compile('test-2.capnp'))

    def do_test(self, schema, converter, test_input, expect, message):
        builder = message.get_root(schema)
        converter.to_builder(test_input, builder)
        self.assertEqual(converter.from_reader(builder.as_reader()), expect)
        mr = capnp.MessageReader.from_message_bytes(message.to_message_bytes())
        self.assertEqual(converter.from_reader(mr.get_root(schema)), expect)

    def do_test_error(self, schema, converter, illegal_input, exc_type, regex):
        with self.subTest(illegal_input):
            mb = capnp.MessageBuilder()
            builder = mb.init_root(schema)
            with self.assertRaisesRegex(exc_type, regex):
                converter.to_builder(illegal_input, builder)

    def test_simple_struct(self):

        dt = datetime.datetime(2000, 1, 2, 3, 4, 5, 6, datetime.timezone.utc)
        self.assertNotEqual(dt.microsecond, 0)

        schema = self.loader.struct_schemas['unittest.test_2:TestSimpleStruct']
        converter = objects.DataclassConverter(schema, TestSimpleStruct)
        dataobject = TestSimpleStruct(
            void_field=capnp.VOID,
            bool_field=False,
            int8_field=0,
            int16_field=0,
            int32_field=0,
            int64_field=0,
            uint8_field=0,
            uint16_field=0,
            uint32_field=0,
            uint64_field=0,
            float32_field=0.0,
            float64_field=0.0,
            text_field_1=None,
            text_field_2=None,
            data_field_1=None,
            data_field_2=None,
            int_list_field=None,
            text_list_field=None,
            enum_field=TestSimpleStruct.TestEnum.member1,
            datetime_int_field=dt.replace(microsecond=0),
            datetime_float_field=dt,
            nested_list=None,
        )
        message = capnp.MessageBuilder()
        builder = message.init_root(schema)

        def do_test(**kwargs):
            obj = dataclasses.replace(dataobject, **kwargs)
            self.do_test(
                schema,
                converter,
                obj,
                obj,
                message,
            )

        def do_test_error(exc_type, regex, **kwargs):
            self.do_test_error(
                schema,
                converter,
                dataclasses.replace(dataobject, **kwargs),
                exc_type,
                regex,
            )

        do_test()

        do_test(bool_field=True)
        self.assertEqual(builder['int32Field'], 0)
        builder['int32Field'] = 42

        self.assertIsNone(builder['nestedList'])
        do_test(
            text_field_1='hello',
            text_field_2='world',
            data_field_1=b'\x00\x01\x02',
            data_field_2=b'\x03\x04\x05',
            nested_list=[
                [
                    [],
                ],
                [
                    [],
                    [(0, )],
                ],
                [
                    [(1, ), (2, )],
                ],
            ],
        )
        self.assertEqual(builder['int32Field'], 0)
        self.assertEqual(len(builder['nestedList']), 3)

        do_test(
            int_list_field=[1, 2, 3],
            text_list_field=[],
        )
        self.assertEqual(len(builder['intListField']), 3)
        self.assertEqual(len(builder['textListField']), 0)
        do_test(
            int_list_field=[1],
            text_list_field=['a', 'b', 'c'],
        )
        self.assertEqual(len(builder['intListField']), 1)
        self.assertEqual(len(builder['textListField']), 3)

        self.assertEqual(builder['enumField'], 1)
        do_test(enum_field=TestSimpleStruct.TestEnum.member2)
        self.assertEqual(builder['enumField'], 2)

        do_test_error(
            AssertionError,
            r'expect .*VoidType.*, not 1',
            void_field=1,
        )
        do_test_error(
            AssertionError,
            r'expect .*VoidType.*, not None',
            void_field=None,
        )

        do_test_error(
            AssertionError,
            r'expect .*str.*-typed value',
            text_field_1=b'',
        )

        do_test_error(
            RuntimeError,
            r'Value out-of-range for requested type.; value = 129',
            int8_field=129,
        )

    def test_invalid_datetime_type_struct(self):
        for schema, dataclass, regex in (
            (
                self.loader.
                struct_schemas['unittest.test_2:TestInvalidDatetimeIntStruct'],
                TestInvalidDatetimeIntStruct,
                r'expect capnp._capnp.Which.INT16 in frozenset',
            ),
            (
                self.loader.struct_schemas[
                    'unittest.test_2:TestInvalidDatetimeFloatStruct'],
                TestInvalidDatetimeFloatStruct,
                r'expect capnp._capnp.Which.FLOAT32 in frozenset',
            ),
        ):
            with self.assertRaisesRegex(TypeError, regex):
                objects.DataclassConverter(schema, dataclass)

    def test_pointer_struct(self):

        name = 'unittest.test_2:TestPointerStruct'
        schema = self.loader.struct_schemas[name]
        converter = objects.DataclassConverter(schema, TestPointerStruct)
        dataobject = TestPointerStruct(
            group_field=None,
            tuple_field_1=None,
            tuple_field_2=None,
            exception_field_1=None,
            exception_field_2=None,
            struct_field=None,
        )
        message = capnp.MessageBuilder()
        builder = message.init_root(schema)

        self.do_test(
            schema,
            converter,
            dataobject,
            dataclasses.replace(
                dataobject,
                group_field=TestPointerStruct.GroupField(group_int_field=0),
                tuple_field_2=(0, ),
                exception_field_2=TestPointerStruct.TestException2(0),
            ),
            message,
        )
        self.assertIsNone(builder['tupleField1'])
        self.assertIsNone(builder['exceptionField1'])
        self.assertIsNone(builder['structField'])

        self.do_test(
            schema,
            converter,
            dataclasses.replace(
                dataobject,
                tuple_field_1=(13, ),
                tuple_field_2=(42, ),
                exception_field_1=TestPointerStruct.TestException(),
                struct_field=TestPointerStruct.EmptyStruct(),
            ),
            dataclasses.replace(
                dataobject,
                group_field=TestPointerStruct.GroupField(group_int_field=0),
                tuple_field_1=(13, ),
                tuple_field_2=(42, ),
                exception_field_1=TestPointerStruct.TestException(),
                exception_field_2=TestPointerStruct.TestException2(0),
                struct_field=TestPointerStruct.EmptyStruct(),
            ),
            message,
        )
        self.assertIsNotNone(builder['tupleField1'])
        self.assertIsNotNone(builder['exceptionField1'])
        self.assertIsNotNone(builder['structField'])

    def test_union_struct(self):

        schema = self.loader.struct_schemas['unittest.test_2:TestUnionStruct']
        converter = objects.DataclassConverter(schema, TestUnionStruct)
        message = capnp.MessageBuilder()
        message.init_root(schema)

        self.do_test(
            schema,
            converter,
            TestUnionStruct(
                u0=None,
                u1=None,
                u2=None,
                m7=None,
                m8=None,
            ),
            TestUnionStruct(
                u0=TestUnionStruct.U0(m0=None, m1=None),
                u1=TestUnionStruct.U1(m2=0, m3=None, m4=None),
                u2=TestUnionStruct.U2(m5=None, m6=None),
                m7=None,
                m8=None,
            ),
            message,
        )

        self.do_test(
            schema,
            converter,
            TestUnionStruct(
                u0=None,
                u1=TestUnionStruct.U1(m2=None, m3=capnp.VOID, m4=None),
                u2=None,
                m7=None,
                m8=None,
            ),
            TestUnionStruct(
                u0=TestUnionStruct.U0(m0=None, m1=None),
                u1=TestUnionStruct.U1(m2=None, m3=None, m4=None),
                u2=TestUnionStruct.U2(m5=None, m6=None),
                m7=None,
                m8=None,
            ),
            message,
        )

        self.do_test(
            schema,
            converter,
            TestUnionStruct(
                u0=TestUnionStruct.U0(m0=None, m1='spam'),
                u1=TestUnionStruct.U1(m2=None, m3=None, m4=b'egg'),
                u2=TestUnionStruct.U2(
                    m5=None,
                    m6=TestPointerStruct.EmptyStruct(),
                ),
                m7=None,
                m8=False,
            ),
            TestUnionStruct(
                u0=TestUnionStruct.U0(m0=None, m1='spam'),
                u1=TestUnionStruct.U1(m2=None, m3=None, m4=b'egg'),
                u2=TestUnionStruct.U2(
                    m5=None,
                    m6=TestPointerStruct.EmptyStruct(),
                ),
                m7=None,
                m8=False,
            ),
            message,
        )

        self.do_test(
            schema,
            converter,
            TestUnionStruct(
                u0=None,
                u1=None,
                u2=None,
                m7=None,
                m8=None,
            ),
            TestUnionStruct(
                u0=TestUnionStruct.U0(m0=None, m1=None),
                u1=TestUnionStruct.U1(m2=0, m3=None, m4=None),
                u2=TestUnionStruct.U2(m5=None, m6=None),
                m7=None,
                m8=False,
            ),
            message,
        )

    def test_nested_union_struct(self):

        schema = self.loader.struct_schemas[
            'unittest.test_2:TestNestedUnionStruct']
        converter = objects.DataclassConverter(schema, TestNestedUnionStruct)
        message = capnp.MessageBuilder()
        builder = message.init_root(schema)

        self.do_test(
            schema,
            converter,
            TestNestedUnionStruct(
                u0=None,
                u1=None,
            ),
            TestNestedUnionStruct(
                u0=TestNestedUnionStruct.U0(m0=False, m1=None, m2=None),
                u1=None,
            ),
            message,
        )

        self.assertIsNotNone(builder['u0'])
        self.assertIsNone(builder['u1'])
        builder.init('u1')
        self.assertIsNone(builder['u0'])
        self.assertIsNotNone(builder['u1'])

        self.do_test(
            schema,
            converter,
            TestNestedUnionStruct(
                u0=TestNestedUnionStruct.U0(m0=True, m1=None, m2=None),
                u1=None,
            ),
            TestNestedUnionStruct(
                u0=TestNestedUnionStruct.U0(m0=True, m1=None, m2=None),
                u1=None,
            ),
            message,
        )

        self.do_test(
            schema,
            converter,
            TestNestedUnionStruct(
                u0=None,
                u1=TestNestedUnionStruct.U1(m3='', m4=None),
            ),
            TestNestedUnionStruct(
                u0=None,
                u1=TestNestedUnionStruct.U1(m3='', m4=None),
            ),
            message,
        )

    def test_recursive_struct(self):
        schema = self.loader.struct_schemas['unittest.test_2:RecursiveStruct']
        dataobject = RecursiveStruct(struct_field=None)
        dataobject = RecursiveStruct(struct_field=dataobject)
        dataobject = RecursiveStruct(struct_field=dataobject)
        dataobject = RecursiveStruct(struct_field=dataobject)
        message = capnp.MessageBuilder()
        builder = message.init_root(schema)
        with self.assertLogs(level='DEBUG') as cm:
            converter = objects.DataclassConverter(schema, RecursiveStruct)
        self.assertEqual(len(cm.output), 1)
        self.assertRegex(
            cm.output[0],
            r'compile struct converter for: .*RecursiveStruct',
        )
        self.do_test(schema, converter, dataobject, dataobject, message)
        self.assertEqual(
            str(builder),
            '(structField = (structField = (structField = ())))',
        )

    def test_sub_type(self):
        schema = self.loader.struct_schemas['unittest.test_2:TestSubType']
        converter = objects.DataclassConverter(schema, TestSubType)
        dataobject = TestSubType(
            int_sub_type=IntSubType(1),
            int_sub_type_union=TestSubType.IntSubTypeUnion(
                int_sub_type=IntSubType(2),
                irrelevant=None,
            ),
        )

        def do_test(reader):
            actual = converter.from_reader(reader)
            self.assertEqual(actual, dataobject)

            self.assertIs(type(actual.int_sub_type), IntSubType)
            self.assertEqual(actual.int_sub_type, 1)

            self.assertIs(
                type(actual.int_sub_type_union.int_sub_type), IntSubType
            )
            self.assertEqual(actual.int_sub_type_union.int_sub_type, 2)
            self.assertIsNone(actual.int_sub_type_union.irrelevant)

        message = capnp.MessageBuilder()
        builder = message.init_root(schema)
        converter.to_builder(dataobject, builder)
        do_test(builder.as_reader())

        mr = capnp.MessageReader.from_message_bytes(message.to_message_bytes())
        do_test(mr.get_root(schema))


if __name__ == '__main__':
    unittest.main()
