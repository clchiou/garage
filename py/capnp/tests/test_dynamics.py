import unittest

from tests.fixtures import Fixture

import capnp


class DynamicsTest(Fixture):

    def test_message_builder(self):

        with capnp.SchemaLoader() as loader:
            loader.load_bytes(self.compile('test-1.capnp'))
            struct_schema = loader.declarations[0]
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
