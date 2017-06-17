import unittest

from tests.fixtures import Fixture

import capnp
import capnp.dynamics


class DynamicsTest(Fixture):

    def setUp(self):
        self.loader = capnp.SchemaLoader()
        self.loader.open()
        self.loader.load_bytes(self.compile('test-1.capnp'))
        self.struct_schema = \
            self.loader.get_schema('unittest.test_1:SomeStruct')
        self.enum_schema = self.loader.get_schema('unittest.test_1:SomeEnum')

    def tearDown(self):
        self.loader.close()

    def test_message_builder(self):

        enum_class = self.enum_schema.generate_enum()

        with capnp.MessageBuilder() as message:

            struct = message.init_root(self.struct_schema)
            struct['b'] = False
            struct['i8'] = -1
            struct['u8'] = 42
            struct['f32'] = 3.14
            struct['t'] = 'hello "" world'
            struct['d'] = b'hello world'
            struct['e'] = enum_class.E1
            struct['u']['v'] = None
            struct['g']['i8'] = 1
            struct['g']['f32'] = 0.1

            struct.init('l', 1).init(0, 1).init(0, 1)[0] = 1

            struct.init('s1').init('s2').init('s3')['i32'] = 42
            (struct
             .init('ls1', 1)[0]
             .init('ls2', 1)[0]
             .init('ls3', 1)[0]['i32']) = 42

            struct.init('gt')['t'] = 'text generic'
            struct.init('gl').init('t', 1)[0] = b'list generic'
            struct.init('gs').init('t').init('s2').init('s3')['i32'] = -77

            self.assertEqual(
                self.encode('test-1.capnp', self.struct_schema, struct),
                message.to_bytes(),
            )

            self.assertEqual(
                self.encode(
                    'test-1.capnp', self.struct_schema, struct,
                    packed=True,
                ),
                message.to_packed_bytes(),
            )

            obj = capnp.DynamicObject(struct)
            self.assertEqual(-1, obj.i8)
            self.assertEqual(-1, obj.I8)  # Upper snake case works, too.
            with self.assertRaises(AttributeError):
                obj.no_such_field

    def test_clear_field(self):
        with capnp.MessageBuilder() as message:
            struct = message.init_root(self.struct_schema)

            with self.assertRaises(KeyError):
                del struct['s1']

            struct.init('s1')
            self.assertTrue('s1' in struct)

            del struct['s1']
            self.assertFalse('s1' in struct)

    def test_any_pointer(self):

        with capnp.MessageBuilder() as message:
            struct = message.init_root(self.struct_schema)
            struct['ap'] = 'text'
            ap = struct['ap']
            self.assertIs(ap.kind, capnp.dynamics.AnyPointer.Kind.LIST)
            self.assertFalse(ap._is_reader)
            self.assertEqual('text', ap.get(str))
            self.assertEqual(b'text\x00', ap.get(bytes))
            mb1 = message.to_bytes()

            ap.init(self.struct_schema)['t'] = 'some message'
            self.assertIs(ap.kind, capnp.dynamics.AnyPointer.Kind.STRUCT)
            mb2 = message.to_bytes()

            ap.set(b'xyz')
            self.assertIs(ap.kind, capnp.dynamics.AnyPointer.Kind.LIST)
            self.assertEqual(b'xyz', ap.get(bytes))
            mb3 = message.to_bytes()

            self.assertIn('ap', struct)
            ap.set(None)
            self.assertNotIn('ap', struct)
            self.assertIs(ap.kind, capnp.dynamics.AnyPointer.Kind.NULL)
            self.assertIsNone(ap.get(bytes))
            mb4 = message.to_bytes()

        with capnp.MessageReader.from_bytes(mb1) as message:
            struct = message.get_root(self.struct_schema)
            ap = struct['ap']
            self.assertIs(ap.kind, capnp.dynamics.AnyPointer.Kind.LIST)
            self.assertTrue(ap._is_reader)
            self.assertEqual('text', ap.get(str))
            self.assertEqual(b'text\x00', ap.get(bytes))

        with capnp.MessageReader.from_bytes(mb2) as message:
            struct = message.get_root(self.struct_schema)
            ap = struct['ap']
            self.assertIs(ap.kind, capnp.dynamics.AnyPointer.Kind.STRUCT)
            self.assertEqual('some message', ap.get(self.struct_schema)['t'])

        with capnp.MessageReader.from_bytes(mb3) as message:
            struct = message.get_root(self.struct_schema)
            ap = struct['ap']
            self.assertEqual(b'xyz', ap.get(bytes))

        with capnp.MessageReader.from_bytes(mb4) as message:
            struct = message.get_root(self.struct_schema)
            self.assertNotIn('ap', struct)

    def test_struct_init_any_pointer(self):

        with capnp.MessageBuilder() as message:
            struct = message.init_root(self.struct_schema)
            struct.init('ap').set('text message')
            mb = message.to_bytes()

        with capnp.MessageReader.from_bytes(mb) as message:
            struct = message.get_root(self.struct_schema)
            ap = struct['ap']
            self.assertIs(ap.kind, capnp.dynamics.AnyPointer.Kind.LIST)
            self.assertEqual('text message', ap.get(str))

    def test_struct_set_any_pointer(self):

        with capnp.MessageBuilder() as message:
            struct = message.init_root(self.struct_schema)
            self.assertNotIn('ap', struct)
            with self.assertRaises(AssertionError):
                struct['ap'] = 1
            self.assertNotIn('ap', struct)  # Transaction semantics.


if __name__ == '__main__':
    unittest.main()
