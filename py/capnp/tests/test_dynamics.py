import unittest

import collections

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

    def test_dynamic_object(self):

        obj = capnp.DynamicObject._make(
            capnp.MessageBuilder(),
            self.struct_schema,
        )
        obj.i8 = -1
        obj._init('l', 1)._init(0, 1)._init(0, 1)[0] = 1
        obj.u = {'b': False}

        self.assertEqual(
            self.encode('test-1.capnp', self.struct_schema, obj._struct),
            obj._message.to_bytes(),
        )

        self.assertEqual(
            collections.OrderedDict([
                ('b', True),
                ('i8', -1),
                ('i16', 2),
                ('i32', 3),
                ('i64', 4),
                ('u8', 0),
                ('u16', 0),
                ('u32', 0),
                ('u64', 0),
                ('f32', 0.0),
                ('f64', 0.0),
                ('e', 1),
                ('l', [[[1]]]),
                ('u', collections.OrderedDict([('b', False)])),
                ('g', collections.OrderedDict([('i8', 0), ('f32', 0.0)])),
            ]),
            obj._serialize_asdict(),
        )

        self.assertEqual(
            [
                ('b', True),
                ('i8', -1),
                ('i16', 2),
                ('i32', 3),
                ('i64', 4),
                ('u8', 0),
                ('u16', 0),
                ('u32', 0),
                ('u64', 0),
                ('f32', 0.0),
                ('f64', 0.0),
                ('e', 1),
                ('l', obj.l),
                ('u', obj.u),
                ('g', obj.g),
            ],
            list(obj._items()),
        )

        # Test field copy.
        o2 = capnp.DynamicObject._make(
            capnp.MessageBuilder(),
            self.struct_schema,
        )
        o2.i8 = obj.i8
        o2.l = obj.l
        o2.u = obj.u
        self.assertEqual(str(obj), str(o2))

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

            # Test reader's __eq__ and __hash__.
            bs = self.encode('test-1.capnp', self.struct_schema, struct)
            with capnp.MessageReader.from_bytes(bs) as m2:

                s1 = struct.as_reader()
                s2 = m2.get_root(self.struct_schema)
                self.assertIsNot(s1, s2)
                self.assertEqual(s1, s2)
                self.assertNotEqual(struct, s2)  # Reader != builder.
                self.assertEqual(hash(s1), hash(s2))

                o1 = capnp.DynamicObject(s1)
                o2 = capnp.DynamicObject(s2)
                self.assertIsNot(o1, o2)
                self.assertEqual(o1, o2)
                self.assertNotEqual(capnp.DynamicObject(struct), o2)
                self.assertEqual(hash(o1), hash(o2))

            # Test builder's __eq__ and __hash__.
            with capnp.MessageBuilder() as m2:

                s2 = m2.init_root(self.struct_schema)
                s2.copy_from(struct)
                self.assertIsNot(struct, s2)
                self.assertEqual(struct, s2)

                o1 = capnp.DynamicObject(struct)
                o2 = capnp.DynamicObject(s2)
                self.assertIsNot(o1, o2)
                self.assertEqual(o1, o2)

            # Builder is not hashable.
            with self.assertRaisesRegex(TypeError, r'unhashable type'):
                hash(struct)
            with self.assertRaisesRegex(TypeError, r'unhashable type'):
                hash(capnp.DynamicObject(struct))

            obj = capnp.DynamicObject(struct)
            self.assertEqual(-1, obj.i8)
            self.assertEqual(-1, obj.I8)  # Upper snake case works, too.
            with self.assertRaises(AttributeError):
                obj.no_such_field

            obj.i8 = 7
            self.assertEqual(7, obj.i8)

            self.assertEqual('hello "" world', obj.t)
            obj.t = 'some text'
            self.assertEqual('some text', obj.t)
            del obj.t
            self.assertIsNone(obj.t)

            self.assertEqual('[[[e1]]]', str(obj.l))
            obj.l = [[[0, 1], [1], [0]]]
            self.assertEqual('[[[e0, e1], [e1], [e0]]]', str(obj.l))

            self.assertEqual('(s2 = (s3 = (i32 = 42)))', str(obj.s1))
            obj.s1 = {'s2': {'s3': {'i32': 99}}}
            self.assertEqual('(s2 = (s3 = (i32 = 99)))', str(obj.s1))

            obj._init('s1').s2 = {'s3': {'i32': 12}}
            self.assertEqual('(s2 = (s3 = (i32 = 12)))', str(obj.s1))

            with capnp.MessageBuilder() as m2:
                s2 = m2.init_root(self.struct_schema)
                s2.copy_from(struct)
                decode = lambda m: self.decode(
                    'test-1.capnp', self.struct_schema, m.to_bytes())
                self.assertEqual(decode(message), decode(m2))

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
