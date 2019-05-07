import unittest

from capnp import _capnp  # pylint: disable=unused-import

try:
    from capnp import _capnp_test
except ImportError:
    _capnp_test = None

# pylint: disable=c-extension-no-member


@unittest.skipUnless(_capnp_test, '_capnp_test unavailable')
class DynamicTest(unittest.TestCase):

    def test_qualname(self):
        for qualname in (
            'DynamicValue',
            'DynamicValue.Reader',
            'DynamicValue.Builder',
            'DynamicStruct',
            'DynamicStruct.Reader',
            'DynamicStruct.Builder',
            'DynamicEnum',
            'DynamicList',
            'DynamicList.Reader',
            'DynamicList.Builder',
        ):
            with self.subTest(qualname):
                obj_type = _capnp
                for path in qualname.split('.'):
                    obj_type = getattr(obj_type, path)
                self.assertEqual(obj_type.__qualname__, qualname)

    def test_dynamic_value(self):

        for cls in (_capnp.DynamicValue.Reader, _capnp.DynamicValue.Builder):

            obj = cls()
            self.assertIs(obj.getType(), _capnp.DynamicValue.Type.UNKNOWN)

            for type_name, init_value in (
                ('VOID', _capnp.VOID),
                ('BOOL', True),
                ('BOOL', False),
                ('INT', -1),
                ('INT', -(1 << 40)),  # Test 64-bit integer.
                ('UINT', 42),
                ('UINT', 1 << 40),  # Test 64-bit integer.
                ('FLOAT', 3.14),
                ('DATA', b'hello world'),
            ):
                with self.subTest((cls, type_name, init_value)):
                    which = _capnp.DynamicValue.Type.names[type_name]

                    name = type_name.capitalize()

                    obj = getattr(cls, 'from%s' % name)(init_value)
                    self.assertIs(obj.getType(), which)

                    value = getattr(obj, 'as%s' % name)()
                    self.assertEqual(value, init_value)

                    if cls is _capnp.DynamicValue.Builder:
                        self.assertIs(obj.asReader().getType(), which)

                    obj2 = cls.fromDynamicValue(obj)
                    self.assertIs(obj2.getType(), which)

            for type_name, name in (
                ('ENUM', 'DynamicEnum'),
                ('LIST', 'DynamicList'),
                ('STRUCT', 'DynamicStruct'),
            ):
                with self.subTest((cls, type_name)):
                    which = _capnp.DynamicValue.Type.names[type_name]

                    type_ = getattr(_capnp, name)
                    if type_name == 'ENUM':
                        pass
                    elif cls is _capnp.DynamicValue.Reader:
                        type_ = getattr(type_, 'Reader')
                    else:
                        type_ = getattr(type_, 'Builder')
                    init_value = type_()

                    obj = getattr(cls, 'from%s' % name)(init_value)
                    self.assertIs(obj.getType(), which)

                    value = getattr(obj, 'as%s' % name)()
                    self.assertIsInstance(value, type_)

                    if cls is _capnp.DynamicValue.Builder:
                        self.assertIs(obj.asReader().getType(), which)

                    obj2 = cls.fromDynamicValue(obj)
                    self.assertIs(obj2.getType(), which)

        obj = _capnp.DynamicValue.Reader.fromText('hello world')
        self.assertIs(obj.getType(), _capnp.DynamicValue.Type.TEXT)
        self.assertEqual(obj.asText(), b'hello world')

    def test_dynamic_struct(self):
        for cls in (_capnp.DynamicStruct.Reader, _capnp.DynamicStruct.Builder):
            with self.subTest(cls):
                obj = cls()

                size = obj.totalSize()
                self.assertEqual(size.wordCount, 0)
                self.assertEqual(size.capCount, 0)

                field = _capnp_test.makeStructSchemaField()
                self.assertTrue(obj.has(field, _capnp.HasMode.NON_NULL))
                self.assertFalse(obj.has(field, _capnp.HasMode.NON_DEFAULT))
                with self.assertRaisesRegex(
                    RuntimeError,
                    r'struct has no such member',
                ):
                    obj.has('no_such_field', _capnp.HasMode.NON_NULL)
                with self.assertRaisesRegex(
                    RuntimeError,
                    r'struct has no such member',
                ):
                    obj.has('no_such_field', _capnp.HasMode.NON_DEFAULT)

                if cls is _capnp.DynamicStruct.Builder:
                    self.assertIsInstance(
                        obj.asReader(),
                        _capnp.DynamicStruct.Reader,
                    )

    def test_dynamic_enum(self):
        obj = _capnp.DynamicEnum()
        self.assertEqual(obj.getRaw(), 0)

    def test_dynamic_list(self):
        for cls in (_capnp.DynamicList.Reader, _capnp.DynamicList.Builder):
            with self.subTest(cls):
                obj = cls()
                self.assertEqual(len(obj), 0)
                self.assertEqual(list(obj), [])
                if cls is _capnp.DynamicList.Builder:
                    self.assertIsInstance(
                        obj.asReader(),
                        _capnp.DynamicList.Reader,
                    )


if __name__ == '__main__':
    unittest.main()
