import unittest

import contextlib
import uuid

from g1 import tests

import nng
from nng import sockets


class SocketTest(unittest.TestCase):

    def test_reqrep(self):

        def do_test(s0, s1):
            f = tests.spawn(s0.send, b'hello world')
            d = s1.recv()
            f.result()
            self.assertEqual(d, b'hello world')

            f = tests.spawn(s1.send, b'spam egg')
            d = s0.recv()
            f.result()
            self.assertEqual(d, b'spam egg')

        with contextlib.ExitStack() as stack:
            url = 'inproc://%s' % uuid.uuid4()

            sock1 = stack.enter_context(sockets.Socket(nng.Protocols.REP0))
            sock1.listen(url)

            sock0 = stack.enter_context(sockets.Socket(nng.Protocols.REQ0))
            sock0.dial(url)

            with self.subTest((sock0, sock1)):
                do_test(sock0, sock1)

            c0 = stack.enter_context(sockets.Context(sock0))
            c1 = stack.enter_context(sockets.Context(sock1))
            with self.subTest((c0, c1)):
                do_test(c0, c1)

    def test_reqrep_incorrect_sequence(self):

        def do_test(s0, s1):
            with self.assertRaises(nng.ERRORS.NNG_ESTATE):
                s0.recv()
            with self.assertRaises(nng.ERRORS.NNG_ESTATE):
                s1.send(b'')

        with contextlib.ExitStack() as stack:
            url = 'inproc://%s' % uuid.uuid4()

            sock1 = stack.enter_context(sockets.Socket(nng.Protocols.REP0))
            sock1.listen(url)

            sock0 = stack.enter_context(sockets.Socket(nng.Protocols.REQ0))
            sock0.dial(url)

            with self.subTest((sock0, sock1)):
                do_test(sock0, sock1)

            c0 = stack.enter_context(sockets.Context(sock0))
            c1 = stack.enter_context(sockets.Context(sock1))
            with self.subTest((c0, c1)):
                do_test(c0, c1)

    def test_dialer_start(self):
        with contextlib.ExitStack() as stack:
            url = 'inproc://%s' % uuid.uuid4()

            s1 = stack.enter_context(sockets.Socket(nng.Protocols.REP0))
            s1.listen(url)

            s0 = stack.enter_context(sockets.Socket(nng.Protocols.REQ0))
            d = s0.dial(url, create_only=True)
            d.start()

            f = tests.spawn(s0.send, b'hello world')
            d = s1.recv()
            f.result()
            self.assertEqual(d, b'hello world')

            d = s0.dial('inproc://%s' % uuid.uuid4())
            with self.assertRaises(nng.ERRORS.NNG_ESTATE):
                d.start()

    def test_message(self):

        def do_test(s0, s1):
            m0 = nng.Message(b'hello world')
            self.assertEqual(m0.header.memory_view, b'')
            self.assertEqual(m0.body.memory_view, b'hello world')

            f = tests.spawn(s0.sendmsg, m0)
            m1 = s1.recvmsg()
            f.result()
            del m0

            self.assertEqual(m1.header.memory_view, b'')
            self.assertEqual(m1.body.memory_view, b'hello world')

            m1.body.memory_view[:] = bytes(reversed(b'hello world'))
            self.assertEqual(m1.header.memory_view, b'')
            self.assertEqual(m1.body.memory_view, b'dlrow olleh')

            f = tests.spawn(s1.sendmsg, m1)
            m2 = s0.recvmsg()
            f.result()
            # Ownership is transferred on success.
            self.assertIsNone(m1._msg_p)

            # Now m2's header has some data.
            self.assertEqual(len(m2.header), 4)
            self.assertEqual(m2.body.memory_view, b'dlrow olleh')

        with contextlib.ExitStack() as stack:
            url = 'inproc://%s' % uuid.uuid4()

            sock1 = stack.enter_context(sockets.Socket(nng.Protocols.REP0))
            sock1.listen(url)

            sock0 = stack.enter_context(sockets.Socket(nng.Protocols.REQ0))
            sock0.dial(url)

            with self.subTest((sock0, sock1)):
                do_test(sock0, sock1)

            c0 = stack.enter_context(sockets.Context(sock0))
            c1 = stack.enter_context(sockets.Context(sock1))
            with self.subTest((c0, c1)):
                do_test(c0, c1)


if __name__ == '__main__':
    unittest.main()
