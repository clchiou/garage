import unittest

from tests.fixtures import Fixture

import capnp


class SchemasTest(Fixture):

    def test_load_from_file(self):
        # This is just a smoking test.
        with self.using_temp_file(self.compile('test-1.capnp')) as path:
            with capnp.SchemaLoader() as loader:
                loader.load_file(path)
                self.assertEqual(1, len(loader.files))

    def test_loader(self):
        with capnp.SchemaLoader() as loader:
            loader.load_bytes(self.compile('test-1.capnp'))

            # loader.files

            self.assertEqual(1, len(loader.files))

            self.assertEqual(
                [str(self.TESTDATA_PATH / 'test-1.capnp')],
                [file_node.name for file_node in loader.files.values()],
            )

            file_node = next(iter(loader.files.values()))

            self.assertEqual(
                [
                    (
                        capnp.Annotation.Kind.CXX_NAMESPACE,
                        'unittest::test_1',
                    ),
                ],
                [
                    (
                        annotation.kind,
                        annotation.value,
                    )
                    for annotation in file_node.annotations
                ],
            )

            # loader.declarations

            self.assertEqual(
                [nn.id for nn in file_node.nested_nodes],
                [decl.id for decl in loader.declarations],
            )

            # loader._schema_lookup_table

            # It should not include union and group field.
            self.assertEqual(
                {
                    'unittest.test_1:SomeEnum',
                    'unittest.test_1:SomeStruct',
                    'unittest.test_1:SomeStruct.EmbeddedStruct1',
                    'unittest.test_1:SomeStruct.EmbeddedStruct2',
                    'unittest.test_1:SomeStruct.EmbeddedStruct3',
                },
                set(loader._schema_lookup_table),
            )

            # SomeStruct

            struct_schema = loader.declarations[0]
            self.assertIs(
                struct_schema,
                loader.get_schema('unittest.test_1:SomeStruct'),
            )
            self.assertEqual('SomeStruct', struct_schema.name)
            self.assertIs(struct_schema.kind, capnp.Schema.Kind.STRUCT)

            self.assertEqual(
                [
                    (
                        capnp.Annotation.Kind.CXX_NAME,
                        'AliasForSomeStruct',
                    ),
                ],
                [
                    (
                        annotation.kind,
                        annotation.value,
                    )
                    for annotation in struct_schema.annotations
                ],
            )

            self.assertEqual(
                [
                    ('b', 0, capnp.Type.Kind.BOOL, (), True),

                    ('i8', 1, capnp.Type.Kind.INT8, (), True),
                    ('i16', 2, capnp.Type.Kind.INT16, (), True),
                    ('i32', 3, capnp.Type.Kind.INT32, (), True),
                    ('i64', 4, capnp.Type.Kind.INT64, (), True),

                    ('u8', 5, capnp.Type.Kind.UINT8, (), False),
                    ('u16', 6, capnp.Type.Kind.UINT16, (), False),
                    ('u32', 7, capnp.Type.Kind.UINT32, (), False),
                    ('u64', 8, capnp.Type.Kind.UINT64, (), False),

                    ('f32', 9, capnp.Type.Kind.FLOAT32, (), False),
                    ('f64', 10, capnp.Type.Kind.FLOAT64, (), False),

                    ('t', 11, capnp.Type.Kind.TEXT, (), True),
                    ('d', 12, capnp.Type.Kind.DATA, (), True),

                    ('e', 13, capnp.Type.Kind.ENUM, (), True),

                    ('l', 14, capnp.Type.Kind.LIST, (), False),

                    ('u', 15, capnp.Type.Kind.STRUCT, (), False),

                    ('g', 16, capnp.Type.Kind.STRUCT, (), False),

                    ('s1', 17, capnp.Type.Kind.STRUCT, (), True),
                    ('ls1', 18, capnp.Type.Kind.LIST, (), True),
                ],
                [
                    (
                        field.name,
                        field.index,
                        field.type.kind,
                        field.annotations,
                        field.has_explicit_default,
                    )
                    for field in struct_schema.fields
                ],
            )

            self.assertIs(True, struct_schema.fields[0].explicit_default)
            self.assertEqual(1, struct_schema.fields[1].explicit_default)
            self.assertEqual(2, struct_schema.fields[2].explicit_default)
            self.assertEqual(3, struct_schema.fields[3].explicit_default)
            self.assertEqual(4, struct_schema.fields[4].explicit_default)
            self.assertEqual(
                'string with "quotes"',
                struct_schema.fields[11].explicit_default,
            )
            self.assertEqual(
                b'\xab\xcd\xef',
                struct_schema.fields[12].explicit_default,
            )
            self.assertEqual(1, struct_schema.fields[13].explicit_default)
            self.assertEqual(
                '(s2 = (s3 = (i32 = 999)))',
                str(struct_schema.fields[17].explicit_default),
            )
            self.assertEqual(
                '[(ls2 = [(ls3 = [(i32 = 999)])])]',
                str(struct_schema.fields[18].explicit_default),
            )

            # SomeEnum

            enum_schema = loader.declarations[1]
            self.assertIs(
                enum_schema,
                loader.get_schema('unittest.test_1:SomeEnum'),
            )
            self.assertEqual('SomeEnum', enum_schema.name)
            self.assertIs(enum_schema.kind, capnp.Schema.Kind.ENUM)

            self.assertEqual(
                [
                    ('e0', 0),
                    ('e1', 1),
                ],
                [
                    (e.name, e.ordinal)
                    for e in enum_schema.enumerants
                ],
            )

            self.assertNotIn('e2', enum_schema)


if __name__ == '__main__':
    unittest.main()
