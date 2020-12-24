import unittest

import ctypes
import gc

from g1.bases import lifecycles

try:
    from g1.devtools import tests
except ImportError:
    tests = None

from nng import _nng
from nng import errors
from nng import messages


class MessageTest(unittest.TestCase):

    def assert_chunk(self, chunk, data):
        self.assertEqual(bool(chunk), bool(data))
        self.assertEqual(len(chunk), len(data))
        self.assertEqual(chunk.copy(), data)
        self.assertEqual(chunk.memory_view, data)
        self.assertEqual(len(chunk.memory_view), len(data))

    @unittest.skipUnless(tests, 'g1.tests unavailable')
    def test_del_not_resurrecting(self):
        tests.assert_del_not_resurrecting(
            self, lambda: messages.Message(b'hello world')
        )

    def test_message(self):
        m = messages.Message()
        self.assert_chunk(m.header, b'')
        self.assert_chunk(m.body, b'')

        m.header.append(b'hello world')
        m.body.append(b'spam egg')
        self.assert_chunk(m.header, b'hello world')
        self.assert_chunk(m.body, b'spam egg')

        m.header.memory_view[0:3] = b'abc'
        m.body.memory_view[0:3] = b'def'
        self.assert_chunk(m.header, b'abclo world')
        self.assert_chunk(m.body, b'defm egg')

        m.header.clear()
        m.body.clear()
        self.assert_chunk(m.header, b'')
        self.assert_chunk(m.body, b'')

    def test_init_data(self):
        m = messages.Message(b'hello world')
        self.assert_chunk(m.header, b'')
        self.assert_chunk(m.body, b'hello world')

    def test_copy(self):
        m1 = messages.Message(b'hello world')
        m2 = m1.copy()
        self.assert_chunk(m2.header, b'')
        self.assert_chunk(m2.body, b'hello world')

    def test_del(self):

        def get_num_alive():
            return lifecycles.take_snapshot()[(messages.Message, 'msg_p')]

        gc.collect()
        n = get_num_alive()
        self.assertGreaterEqual(n, 0)

        m1 = messages.Message(b'hello')
        self.assertEqual(get_num_alive(), n + 1)

        m2 = messages.Message(b'world')
        self.assertEqual(get_num_alive(), n + 2)

        m3 = m1.copy()
        self.assertEqual(get_num_alive(), n + 3)

        m4 = messages.Message(msg_p=m1.disown())
        self.assertEqual(get_num_alive(), n + 3)

        msg_p = _nng.nng_msg_p()
        errors.check(_nng.F.nng_msg_alloc(ctypes.byref(msg_p), 16))
        m5 = messages.Message(msg_p=msg_p)
        self.assertEqual(get_num_alive(), n + 4)

        del m1, m2, m3, m4, m5
        gc.collect()
        self.assertEqual(get_num_alive(), n)


if __name__ == '__main__':
    unittest.main()
