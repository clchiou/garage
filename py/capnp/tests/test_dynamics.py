import unittest

from tests.fixtures import Fixture

import capnp


class DynamicsTest(Fixture):

    def test_message_builder(self):

        with capnp.SchemaLoader() as loader:
            loader.load_bytes(self.compile('test-1.capnp'))
            struct_schema = loader.get_schema('unittest.test_1:SomeStruct')
            self.assertEqual('SomeStruct', struct_schema.name)

            with capnp.MessageBuilder() as message:

                struct = message.init_root(struct_schema)
                struct['b'] = False
                struct['i8'] = -1
                struct['u8'] = 42
                struct['f32'] = 3.14
                struct['t'] = 'hello "" world'
                struct['d'] = b'hello world'
                struct['e'] = 1
                struct['u']['v'] = None
                struct['g']['i8'] = 1
                struct['g']['f32'] = 0.1

                struct.init('l', 1).init(0, 1).init(0, 1)[0] = 1

                struct.init('s1').init('s2').init('s3')['i32'] = 42
                (struct
                 .init('ls1', 1)[0]
                 .init('ls2', 1)[0]
                 .init('ls3', 1)[0]['i32']) = 42

                self.assertEqual(
                    self.encode('test-1.capnp', struct_schema, struct),
                    message.to_bytes(),
                )

                self.assertEqual(
                    self.encode(
                        'test-1.capnp', struct_schema, struct,
                        packed=True,
                    ),
                    message.to_packed_bytes(),
                )


if __name__ == '__main__':
    unittest.main()
