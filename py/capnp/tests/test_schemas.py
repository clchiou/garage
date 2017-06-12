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
                        capnp.AnnotationDef.Known.CXX_NAMESPACE,
                        'unittest::test_1',
                    ),
                ],
                [
                    (
                        annotation.node.known,
                        annotation.value,
                    )
                    for annotation in file_node.annotations
                ],
            )

            # loader.definitions

            self.assertEqual(
                # Exclude structAnnotation.
                [(nn.id, nn.name) for nn in file_node.nested_nodes[1:]],
                [
                    (definition.id, definition.name)
                    for definition in loader.definitions
                ],
            )

            # loader._schema_lookup_table

            # It should not include union and group field.
            self.assertEqual(
                {
                    'unittest.test_1:anyPointerConst',
                    'unittest.test_1:int8Const',
                    'unittest.test_1:structConst',
                    'unittest.test_1:GenericStruct',
                    'unittest.test_1:SomeEnum',
                    'unittest.test_1:SomeStruct',
                    'unittest.test_1:SomeStruct.EmbeddedStruct1',
                    'unittest.test_1:SomeStruct.EmbeddedStruct2',
                    'unittest.test_1:SomeStruct.EmbeddedStruct3',
                    'unittest.test_1:SomeStruct.someStructConst',
                    'unittest.test_1:StructAnnotation',
                },
                set(loader._schema_lookup_table),
            )

            # SomeStruct

            struct_schema = loader.definitions[2]
            self.assertIs(
                struct_schema,
                loader.get_schema('unittest.test_1:SomeStruct'),
            )
            self.assertEqual('SomeStruct', struct_schema.name)
            self.assertIs(struct_schema.kind, capnp.Schema.Kind.STRUCT)

            self.assertEqual(
                [
                    (
                        capnp.AnnotationDef.Known.CXX_NAME,
                        'AliasForSomeStruct',
                    ),
                ],
                [
                    (
                        annotation.node.known,
                        annotation.value,
                    )
                    for annotation in struct_schema.annotations
                ],
            )

            self.assertEqual(
                [
                    ('b', 0, capnp.Type.Kind.BOOL, False, True),

                    ('i8', 1, capnp.Type.Kind.INT8, False, True),
                    ('i16', 2, capnp.Type.Kind.INT16, False, True),
                    ('i32', 3, capnp.Type.Kind.INT32, False, True),
                    ('i64', 4, capnp.Type.Kind.INT64, False, True),

                    ('u8', 5, capnp.Type.Kind.UINT8, True, False),
                    ('u16', 6, capnp.Type.Kind.UINT16, False, False),
                    ('u32', 7, capnp.Type.Kind.UINT32, False, False),
                    ('u64', 8, capnp.Type.Kind.UINT64, False, False),

                    ('f32', 9, capnp.Type.Kind.FLOAT32, False, False),
                    ('f64', 10, capnp.Type.Kind.FLOAT64, False, False),

                    ('t', 11, capnp.Type.Kind.TEXT, False, True),
                    ('d', 12, capnp.Type.Kind.DATA, False, True),

                    ('e', 13, capnp.Type.Kind.ENUM, False, True),

                    ('l', 14, capnp.Type.Kind.LIST, False, False),

                    ('u', 15, capnp.Type.Kind.STRUCT, False, False),

                    ('g', 16, capnp.Type.Kind.STRUCT, False, False),

                    ('s1', 17, capnp.Type.Kind.STRUCT, False, True),
                    ('ls1', 18, capnp.Type.Kind.LIST, False, True),

                    ('ap', 19, capnp.Type.Kind.ANY_POINTER, False, True),

                    ('gt', 20, capnp.Type.Kind.STRUCT, False, False),
                    ('gl', 21, capnp.Type.Kind.STRUCT, False, False),
                    ('gs', 22, capnp.Type.Kind.STRUCT, False, False),
                    ('gg', 23, capnp.Type.Kind.STRUCT, False, False),
                ],
                [
                    (
                        field.name,
                        field.index,
                        field.type.kind,
                        bool(field.annotations),
                        field.has_explicit_default,
                    )
                    for field in struct_schema.fields
                ],
            )

            # Check annotation value
            self.assertEqual(
                [
                    '(x = 7)',
                ],
                [
                    str(annotation.value)
                    for annotation in struct_schema.fields[5].annotations
                ],
            )

            # Check explicit default value
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
            self.assertEqual(
                '(x = 7)',
                str(struct_schema.fields[19].explicit_default.get(
                    loader.get_schema('unittest.test_1:StructAnnotation'),
                )),
            )

            # Check generics
            self.assertFalse(struct_schema.is_generic)
            self.assertEqual(
                [
                    (True, True, 'GenericStruct(Text)'),
                    (True, True, 'GenericStruct(List(Data))'),
                    (True, True, 'GenericStruct(EmbeddedStruct1)'),
                    (True, False, 'GenericStruct'),
                ],
                [
                    (
                        g.type.schema.is_generic,
                        g.type.schema.is_branded,
                        str(g.type),
                    )
                    for g in (
                        struct_schema['gt'],
                        struct_schema['gl'],
                        struct_schema['gs'],
                        struct_schema['gg'],
                    )
                ],
            )

            # SomeEnum

            enum_schema = loader.definitions[3]
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
                    ('someCamelCaseWord', 2),
                ],
                [
                    (e.name, e.ordinal)
                    for e in enum_schema.enumerants
                ],
            )

            self.assertNotIn('e2', enum_schema)

            enum_class = enum_schema.generate_enum()
            self.assertEqual('SomeEnum', enum_class.__name__)
            self.assertEqual(
                [
                    ('E0', 0),
                    ('E1', 1),
                    ('SOME_CAMEL_CASE_WORD', 2),
                ],
                [
                    (name, member.value)
                    for name, member in enum_class.__members__.items()
                ],
            )

            # Const values

            fqname = 'unittest.test_1:int8Const'
            self.assertEqual(13, loader.get_schema(fqname).value)

            with capnp.MessageBuilder() as message:
                # Construct a default message.
                struct = message.init_root(struct_schema)
                fqname = 'unittest.test_1:SomeStruct.someStructConst'
                self.assertEqual(
                    str(struct),
                    str(loader.get_schema(fqname).value),
                )

            # AnyPointer const value

            value = loader.get_schema('unittest.test_1:anyPointerConst').value
            self.assertEqual(
                '(x = 7)',
                str(value.get(
                    loader.get_schema('unittest.test_1:StructAnnotation'),
                )),
            )


if __name__ == '__main__':
    unittest.main()
