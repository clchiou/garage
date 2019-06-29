import unittest

from pathlib import Path

try:
    from g1.devtools import tests
except ImportError:
    tests = None

from capnp import schemas


@unittest.skipUnless(tests, 'g1.tests unavailable')
@unittest.skipUnless(
    tests and tests.check_program(['capnp', '--version']),
    'capnp unavailable',
)
class SchemaLoaderTest(unittest.TestCase):

    TESTDATA_PATH = Path(__file__).parent / 'testdata'

    @classmethod
    def compile(cls, path):
        path = str(cls.TESTDATA_PATH / path)
        return tests.check_output(['capnp', 'compile', '-o-', path])

    def test_schema_loader(self):

        structs = (
            ('StructAnnotation', ('x', )),
            ('AliasForStruct1', ()),
            ('AliasForStruct1.AliasForStruct2', ()),
            (
                'SomeStruct',
                (
                    'b',
                    'i8',
                    'i16',
                    'i32',
                    'i64',
                    'u8',
                    'u16',
                    'u32',
                    'u64',
                    'f32',
                    'f64',
                    't1',
                    'd1',
                    't2',
                    'd2',
                    'e',
                    'l',
                    'u',
                    'g',
                    's1',
                    'ls1',
                    'ap',
                    'gt',
                    'gl',
                    'gs',
                    'gg',
                ),
            ),
            ('SomeStruct.u', ('v', 'b')),
            ('SomeStruct.g', ('i8', 'f32')),
            ('SomeStruct.EmbeddedStruct1', ('s2', 'ls2')),
            ('SomeStruct.EmbeddedStruct2', ('s3', 'ls3')),
            ('SomeStruct.EmbeddedStruct3', ('i32', )),
            ('GenericStruct', ('t', )),
        )

        enums = (('SomeEnum', ('e0', 'e1', 'someCamelCaseWord')), )

        consts = (
            ('int8Const', 'is_int8'),
            ('SomeStruct.someStructConst', 'is_struct'),
            ('structConst', 'is_struct'),
            ('anyPointerConst', 'is_any_pointer'),
        )

        with schemas.SchemaLoader() as loader:
            loader.load_once(self.compile('test-1.capnp'))

            self.assertEqual(
                sorted(loader.files),
                [
                    'capnp/c++.capnp',
                    'tests/testdata/test-1.capnp',
                ],
            )

            for object_path, details in structs:
                with self.subTest(object_path):
                    label = 'unittest.test_1:%s' % object_path
                    self.assertIn(label, loader.struct_schemas)
                    struct_schema = loader.struct_schemas[label]
                    self.assertTrue(struct_schema.proto.is_struct())
                    self.assertEqual(tuple(struct_schema.fields), details)
                    indexes = [f.index for f in struct_schema.fields.values()]
                    self.assertEqual(indexes, sorted(indexes))
            self.assertEqual(len(loader.struct_schemas), len(structs))

            for object_path, details in enums:
                with self.subTest(object_path):
                    label = 'unittest.test_1:%s' % object_path
                    self.assertIn(label, loader.enum_schemas)
                    enum_schema = loader.enum_schemas[label]
                    self.assertTrue(enum_schema.proto.is_enum())
                    self.assertEqual(tuple(enum_schema.enumerants), details)
                    indexes = [
                        e.index for e in enum_schema.enumerants.values()
                    ]
                    self.assertEqual(indexes, sorted(indexes))
            self.assertEqual(len(loader.enum_schemas), len(enums))

            self.assertEqual(loader.interface_schemas, {})

            for object_path, details in consts:
                with self.subTest(object_path):
                    label = 'unittest.test_1:%s' % object_path
                    self.assertIn(label, loader.const_schemas)
                    const_schema = loader.const_schemas[label]
                    self.assertTrue(const_schema.proto.is_const())
                    self.assertTrue(getattr(const_schema.type, details)())
            self.assertEqual(len(loader.const_schemas), len(consts))

            self.assertEqual(
                sorted(loader.annotations),
                [
                    'capnp.annotations:name',
                    'capnp.annotations:namespace',
                    'unittest.test_1:structAnnotation',
                ],
            )


if __name__ == '__main__':
    unittest.main()
