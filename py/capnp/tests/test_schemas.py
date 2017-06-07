import unittest

from tests.fixtures import Fixture

import capnp


class SchemasTest(Fixture):

    def test_loader(self):
        with capnp.SchemaLoader() as loader:
            loader.load_bytes(self.compile('test-1.capnp'))

            # loader.files

            self.assertEqual(1, len(loader.files))

            file_node = next(iter(loader.files.values()))
            self.assertEqual(
                str(self.TESTDATA_PATH / 'test-1.capnp'),
                file_node.name,
            )

            self.assertEqual(1, len(file_node.annotations))
            self.assertIs(
                file_node.annotations[0].kind,
                capnp.Annotation.Kind.CXX_NAMESPACE,
            )
            self.assertEqual(
                'unittest',
                file_node.annotations[0].value,
            )

            # loader.declarations

            self.assertEqual(2, len(loader.declarations))
            self.assertEqual(
                file_node.node_ids,
                tuple(decl.id for decl in loader.declarations),
            )

            # SomeStruct

            struct_schema = loader.declarations[0]
            self.assertIs(struct_schema.kind, capnp.Schema.Kind.STRUCT)

            self.assertEqual(1, len(struct_schema.annotations))
            self.assertIs(
                struct_schema.annotations[0].kind,
                capnp.Annotation.Kind.CXX_NAME,
            )
            self.assertEqual(
                'AliasForSomeStruct',
                struct_schema.annotations[0].value,
            )

            self.assertEqual(
                (
                    'boolWithDefault',
                    'i8', 'i16', 'i32', 'i64',
                    'u8', 'u16', 'u32', 'u64',
                    'f32', 'f64',
                    't', 'd',
                    'e',
                    'l',
                ),
                tuple(struct_schema),
            )

            # SomeEnum

            enum_schema = loader.declarations[1]
            self.assertIs(enum_schema.kind, capnp.Schema.Kind.ENUM)

            self.assertEqual(('e0', 'e1'), tuple(enum_schema))
            self.assertNotIn('e2', enum_schema)


if __name__ == '__main__':
    unittest.main()
