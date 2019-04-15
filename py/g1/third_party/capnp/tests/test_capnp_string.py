# -*- coding: utf-8 -*-

import unittest

from capnp import _capnp  # pylint: disable=unused-import

try:
    from capnp import _capnp_test
except ImportError:
    _capnp_test = None

# pylint: disable=c-extension-no-member


@unittest.skipUnless(_capnp_test, '_capnp_test unavailable')
class StringTest(unittest.TestCase):

    def test_array_ptr_bytes(self):
        holder = _capnp_test.ArrayPtrBytesHolder()
        self.assertIsInstance(holder.getConst(), memoryview)
        self.assertIsInstance(holder.get(), memoryview)
        self.assertEqual(holder.getConst(), b'')
        self.assertEqual(holder.get(), b'')

        data = b'hello world'
        holder.array = data
        self.assertEqual(holder.getConst(), data)
        self.assertEqual(holder.get(), data)

        holder = _capnp_test.ArrayPtrBytesHolder()
        mview = memoryview(data)
        holder.array = mview
        self.assertEqual(holder.getConst(), data)
        self.assertEqual(holder.get(), data)

    def test_array_ptr_words(self):
        holder = _capnp_test.ArrayPtrWordsHolder()
        self.assertIsInstance(holder.getConst(), memoryview)
        self.assertIsInstance(holder.get(), memoryview)
        self.assertEqual(holder.getConst(), b'')
        self.assertEqual(holder.get(), b'')

        data = b'hello world'
        holder.array = data
        self.assertEqual(holder.getConst(), data)
        self.assertEqual(holder.get(), data)

        holder = _capnp_test.ArrayPtrWordsHolder()
        mview = memoryview(data)
        holder.array = mview
        self.assertEqual(holder.getConst(), data)
        self.assertEqual(holder.get(), data)

    def test_string_ptr(self):
        holder = _capnp_test.StringPtrHolder()
        self.assertIsInstance(holder.get(), memoryview)
        self.assertEqual(bytes(holder.get()), b'')
        self.assertEqual(holder.size(), 0)

        data_str = '你好，世界'
        data = data_str.encode('utf8')
        holder.set(data_str)
        self.assertEqual(holder.get(), data)
        self.assertEqual(holder.size(), len(data))

        holder = _capnp_test.StringPtrHolder()
        mview = memoryview(data)
        holder.set(mview)
        self.assertEqual(holder.get(), data)
        self.assertEqual(holder.size(), len(data))

    def test_string(self):
        holder = _capnp_test.StringPtrHolder()
        data_str = '你好，世界'
        holder.set(data_str)
        string = _capnp_test.toStringTree(holder)
        self.assertEqual(string, data_str)

    def test_data_reader(self):
        holder = _capnp_test.ArrayPtrBytesHolder()
        data = b'hello world'
        holder.array = data
        self.assertIsInstance(holder.asReader(), memoryview)
        self.assertEqual(holder.asReader(), b'hello world')

    def test_text_reader(self):
        holder = _capnp_test.StringPtrHolder()
        data_str = '你好，世界'
        data = data_str.encode('utf8')
        holder.set(data_str)
        self.assertIsInstance(holder.asReader(), memoryview)
        self.assertEqual(holder.asReader(), data)


if __name__ == '__main__':
    unittest.main()
