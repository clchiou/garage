import unittest

import dataclasses
import enum
from pathlib import Path
from typing import Optional

try:
    from g1.devtools import tests
except ImportError:
    tests = None

import capnp
from capnp import objects


@dataclasses.dataclass(frozen=True)
class TestStructOld:

    __name__ = 'TestStruct'

    class TestEnum(enum.Enum):
        old_member = 0

    enum_field: TestEnum
    no_optional_enum_field: type(None)
    optional_enum_field: Optional[TestEnum]


@dataclasses.dataclass(frozen=True)
class TestStructNew:

    __name__ = 'TestStruct'

    class TestEnum(enum.Enum):
        old_member = 0
        new_member = 1

    enum_field: TestEnum
    no_optional_enum_field: type(None)
    optional_enum_field: Optional[TestEnum]
    extra_field: bool


@unittest.skipUnless(tests, 'g1.tests unavailable')
@unittest.skipUnless(
    tests and tests.check_program(['capnp', '--version']),
    'capnp unavailable',
)
class ObjectsCompatibilityTest(unittest.TestCase):

    TESTDATA_PATH = Path(__file__).parent / 'testdata'

    @classmethod
    def compile(cls, path):
        path = str(cls.TESTDATA_PATH / path)
        return tests.check_output(['capnp', 'compile', '-o-', path])

    @classmethod
    def setUpClass(cls):
        cls.loader_old = capnp.SchemaLoader()
        cls.loader_old.load_once(cls.compile('test-compatibility-old.capnp'))
        cls.loader_new = capnp.SchemaLoader()
        cls.loader_new.load_once(cls.compile('test-compatibility-new.capnp'))

        name = 'unittest.test_compatibility:TestStruct'
        cls.schema_old = cls.loader_old.struct_schemas[name]
        cls.converter_old = objects.DataclassConverter(
            cls.schema_old, TestStructOld
        )
        cls.schema_new = cls.loader_new.struct_schemas[name]
        cls.converter_new = objects.DataclassConverter(
            cls.schema_new, TestStructNew
        )

    def test_backward_compatibility(self):
        # Old data, new converter.
        message_old = capnp.MessageBuilder()
        self.converter_old.to_builder(
            TestStructOld(
                enum_field=TestStructOld.TestEnum.old_member,
                no_optional_enum_field=None,
                optional_enum_field=TestStructOld.TestEnum.old_member,
            ),
            message_old.init_root(self.schema_old),
        )

        message_new = capnp.MessageReader.from_message_bytes(
            message_old.to_message_bytes()
        )
        self.assertEqual(
            self.converter_new.from_reader(
                message_new.get_root(self.schema_new)
            ),
            TestStructNew(
                enum_field=TestStructNew.TestEnum.old_member,
                no_optional_enum_field=None,
                optional_enum_field=TestStructNew.TestEnum.old_member,
                extra_field=False,
            ),
        )

    def test_forward_compatibility(self):
        # New data, old converter.
        message_new = capnp.MessageBuilder()
        self.converter_new.to_builder(
            TestStructNew(
                enum_field=TestStructNew.TestEnum.new_member,
                no_optional_enum_field=None,
                optional_enum_field=TestStructNew.TestEnum.new_member,
                extra_field=True,
            ),
            message_new.init_root(self.schema_new),
        )

        message_old = capnp.MessageReader.from_message_bytes(
            message_new.to_message_bytes()
        )
        self.assertEqual(
            self.converter_old.from_reader(
                message_old.get_root(self.schema_old)
            ),
            TestStructOld(
                enum_field=1,
                no_optional_enum_field=None,
                optional_enum_field=1,
            ),
        )


if __name__ == '__main__':
    unittest.main()
