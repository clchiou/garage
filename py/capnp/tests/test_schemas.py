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
                        'unittest',
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

            # SomeStruct

            struct_schema = loader.declarations[0]
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
                    (
                        'b', 0, capnp.Type.Kind.BOOL, (),
                        True, True,
                    ),

                    (
                        'i8', 1, capnp.Type.Kind.INT8, (),
                        True, 1,
                    ),
                    (
                        'i16', 2, capnp.Type.Kind.INT16, (),
                        True, 2,
                    ),
                    (
                        'i32', 3, capnp.Type.Kind.INT32, (),
                        True, 3,
                    ),
                    (
                        'i64', 4, capnp.Type.Kind.INT64, (),
                        True, 4,
                    ),

                    (
                        'u8', 5, capnp.Type.Kind.UINT8, (),
                        False, None,
                    ),
                    (
                        'u16', 6, capnp.Type.Kind.UINT16, (),
                        False, None,
                    ),
                    (
                        'u32', 7, capnp.Type.Kind.UINT32, (),
                        False, None,
                    ),
                    (
                        'u64', 8, capnp.Type.Kind.UINT64, (),
                        False, None,
                    ),

                    (
                        'f32', 9, capnp.Type.Kind.FLOAT32, (),
                        False, None,
                    ),
                    (
                        'f64', 10, capnp.Type.Kind.FLOAT64, (),
                        False, None,
                    ),

                    (
                        't', 11, capnp.Type.Kind.TEXT, (),
                        True, 'string with "quotes"',
                    ),
                    (
                        'd', 12, capnp.Type.Kind.DATA, (),
                        True, b'\xab\xcd\xef'
                    ),

                    (
                        'e', 13, capnp.Type.Kind.ENUM, (),
                        True, 1,
                    ),

                    (
                        'l', 14, capnp.Type.Kind.LIST, (),
                        False, None,
                    ),
                ],
                [
                    (
                        field.name,
                        field.index,
                        field.type.kind,
                        field.annotations,
                        field.has_explicit_default,
                        field.default,
                    )
                    for field in struct_schema.fields
                ],
            )

            # SomeEnum

            enum_schema = loader.declarations[1]
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
