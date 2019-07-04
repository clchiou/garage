import unittest

from pathlib import Path

try:
    from g1.devtools import tests
except ImportError:
    tests = None

import capnp
from capnp import messages
from capnp import schemas


@unittest.skipUnless(tests, 'g1.tests unavailable')
@unittest.skipUnless(
    tests and tests.check_program(['capnp', '--version']),
    'capnp unavailable',
)
class MessagesTest(unittest.TestCase):

    TESTDATA_PATH = Path(__file__).parent / 'testdata'

    @classmethod
    def compile(cls, path):
        path = str(cls.TESTDATA_PATH / path)
        return tests.check_output(['capnp', 'compile', '-o-', path])

    @classmethod
    def setUpClass(cls):
        cls.loader = schemas.SchemaLoader()
        cls.loader.load_once(cls.compile('test-1.capnp'))
        cls.schema = cls.loader.struct_schemas['unittest.test_1:SomeStruct']

    def test_message(self):

        def assert_struct(struct):

            for key, value in (
                ('b', True),
                ('i8', 1),
                ('i16', 2),
                ('i32', 3),
                ('i64', 4),
                ('u8', 0),
                ('u16', 0),
                ('u32', 0),
                ('u64', 0),
                ('f32', 0.0),
                ('f64', 0.0),
                ('t1', 'string with "quotes"'),
                ('d1', b'\xab\xcd\xef'),
                ('t2', None),
                ('d2', None),
                ('e', 1),
                ('l', None),
                ('gt', None),
                ('gl', None),
                ('gs', None),
                ('gg', None),
            ):
                with self.subTest((key, value)):
                    self.assertEqual(struct[key], value)

            u = struct['u']
            self.assertIs(u['v'], capnp.VOID)
            self.assertIsNone(u['b'])

            g = struct['g']
            self.assertEqual(g['i8'], 0)
            self.assertEqual(g['f32'], 0.0)

            self.assertEqual(struct['s1']['s2']['s3']['i32'], 999)
            self.assertIsNone(struct['s1']['ls2'], None)

            ls1 = struct['ls1']
            self.assertEqual(len(ls1), 1)
            self.assertIsNone(ls1[0]['s2'])
            ls2 = ls1[0]['ls2']
            self.assertEqual(len(ls2), 1)
            self.assertIsNone(ls2[0]['s3'])
            ls3 = ls2[0]['ls3']
            self.assertEqual(len(ls3), 1)
            self.assertEqual(ls3[0]['i32'], 999)

            with self.assertRaisesRegex(
                NotImplementedError,
                r'do not support any-pointer for now',
            ):
                struct['ap']  # pylint: disable=pointless-statement

            for name in struct:
                self.assertIn(name, struct)
            self.assertNotIn('notSuchField', struct)

            self.assertEqual(
                str(struct),
                r'('
                r'b = true, i8 = 1, i16 = 2, i32 = 3, i64 = 4, '
                r'u8 = 0, u16 = 0, u32 = 0, u64 = 0, f32 = 0, f64 = 0, '
                r't1 = "string with \"quotes\"", d1 = "\xab\xcd\xef", '
                r'e = e1, u = (v = void), g = (i8 = 0, f32 = 0), '
                r's1 = (s2 = (s3 = (i32 = 999))), '
                r'ls1 = [(ls2 = [(ls3 = [(i32 = 999)])])])',
            )

        mb1 = messages.MessageBuilder()
        struct = mb1.init_root(self.schema)
        assert_struct(struct)
        self.assertFalse(mb1.is_canonical())

        assert_struct(struct.as_reader())

        message_bytes = mb1.to_message_bytes()
        packed_message_bytes = mb1.to_packed_message_bytes()

        mr = messages.MessageReader.from_message_bytes(message_bytes)
        assert_struct(mr.get_root(self.schema))
        self.assertFalse(mr.is_canonical())

        mr = messages.MessageReader.from_packed_message_bytes(
            packed_message_bytes
        )
        assert_struct(mr.get_root(self.schema))
        self.assertFalse(mr.is_canonical())

        mb2 = messages.MessageBuilder()
        mb2.set_root(mr.get_root(self.schema))
        assert_struct(mb2.get_root(self.schema))

    def test_builder(self):
        mb = messages.MessageBuilder()
        struct = mb.init_root(self.schema)

        for key, old_value, new_value in (
            ('b', True, False),
            ('i8', 1, 11),
            ('i16', 2, 12),
            ('i32', 3, 13),
            ('i64', 4, 14),
            ('u8', 0, 15),
            ('u16', 0, 16),
            ('u32', 0, 17),
            ('u64', 0, 18),
            ('f32', 0.0, 3.141),
            ('f64', 0.0, 2.718),
            ('t1', 'string with "quotes"', 'hello'),
            ('d1', b'\xab\xcd\xef', b'spam'),
            ('t2', None, 'world'),
            ('d2', None, b'egg'),
            ('e', 1, 0),
        ):
            with self.subTest((key, old_value, new_value)):

                self.assertEqual(struct[key], old_value)

                struct[key] = new_value
                if isinstance(new_value, float):
                    self.assertAlmostEqual(struct[key], new_value)
                else:
                    self.assertEqual(struct[key], new_value)

                del struct[key]
                self.assertEqual(struct[key], old_value)

                with self.assertRaisesRegex(
                    AssertionError,
                    r'expect.*-typed value, not None',
                ):
                    struct[key] = None

        # pylint: disable=unsubscriptable-object
        # pylint: disable=unsupported-assignment-operation

        self.assertIsNone(struct['l'])
        self.assertEqual(len(struct.init('l', 0)), 0)
        struct.init('l', 1).init(0, 1).init(0, 1)
        self.assertEqual(struct['l'][0][0][0], 0)
        struct['l'][0][0][0] = 1
        self.assertEqual(struct['l'][0][0][0], 1)
        self.assertEqual(len(struct['l']), 1)
        self.assertEqual(len(struct['l'][0]), 1)
        self.assertEqual(len(struct['l'][0][0]), 1)

        self.assertIs(struct['u']['v'], capnp.VOID)
        self.assertIsNone(struct['u']['b'])
        struct['u']['b'] = True
        self.assertIsNone(struct['u']['v'])
        self.assertTrue(struct['u']['b'])

        self.assertIsNone(struct['gt'])
        struct.init('gt')['t'] = 'hello world'
        self.assertEqual(struct['gt']['t'], 'hello world')

        self.assertEqual(
            str(struct),
            r'('
            r'b = true, i8 = 1, i16 = 2, i32 = 3, i64 = 4, '
            r'u8 = 0, u16 = 0, u32 = 0, u64 = 0, f32 = 0, f64 = 0, '
            r't1 = "string with \"quotes\"", d1 = "\xab\xcd\xef", '
            r'e = e1, l = [[[e1]]], u = (b = true), '
            r'g = (i8 = 0, f32 = 0), gt = (t = "hello world")'
            r')',
        )

    def test_from_text(self):
        schema = self.loader.struct_schemas['unittest.test_1:StructAnnotation']
        text = '(x = 34)'
        mb = messages.MessageBuilder()
        struct = mb.init_root(schema)
        struct.from_text(text)
        self.assertEqual(str(mb.get_root(schema)), text)


if __name__ == '__main__':
    unittest.main()
