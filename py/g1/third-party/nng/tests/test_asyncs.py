import unittest

import contextlib
import gc
import uuid

from g1.asyncs import kernels
from g1.asyncs.bases import tasks
from g1.bases import lifecycles

import nng
from nng import asyncs
from nng import messages


def get_num_alive():
    return lifecycles.take_snapshot()[(messages.Message, 'msg_p')]


def checking_alive_msg_p(test_method):

    def wrapper(self):
        gc.collect()
        n = get_num_alive()
        self.assertGreaterEqual(n, 0)
        test_method(self)
        gc.collect()
        self.assertEqual(get_num_alive(), n)

    return wrapper


class SocketTest(unittest.TestCase):

    @kernels.with_kernel
    @checking_alive_msg_p
    def test_reqrep(self):

        def do_test(s0, s1):
            t0 = tasks.spawn(s0.send(b'hello world'))
            t1 = tasks.spawn(s1.recv())
            kernels.run(timeout=1)
            self.assertTrue(t0.is_completed())
            self.assertTrue(t1.is_completed())
            self.assertEqual(t1.get_result_nonblocking(), b'hello world')

            t2 = tasks.spawn(s1.send(b'spam egg'))
            t3 = tasks.spawn(s0.recv())
            kernels.run(timeout=1)
            self.assertTrue(t2.is_completed())
            self.assertTrue(t3.is_completed())
            self.assertEqual(t3.get_result_nonblocking(), b'spam egg')

        with contextlib.ExitStack() as stack:
            url = 'inproc://%s' % uuid.uuid4()

            sock1 = stack.enter_context(asyncs.Socket(nng.Protocols.REP0))
            sock1.listen(url)

            sock0 = stack.enter_context(asyncs.Socket(nng.Protocols.REQ0))
            sock0.dial(url)

            with self.subTest((sock0, sock1)):
                do_test(sock0, sock1)

            c0 = stack.enter_context(asyncs.Context(sock0))
            c1 = stack.enter_context(asyncs.Context(sock1))
            with self.subTest((c0, c1)):
                do_test(c0, c1)

    @kernels.with_kernel
    @checking_alive_msg_p
    def test_reqrep_incorrect_sequence(self):

        def do_test(s0, s1):
            with self.assertRaises(nng.Errors.ESTATE):
                kernels.run(s0.recv(), timeout=1)
            with self.assertRaises(nng.Errors.ESTATE):
                kernels.run(s1.send(b''), timeout=1)

        with contextlib.ExitStack() as stack:
            url = 'inproc://%s' % uuid.uuid4()

            sock1 = stack.enter_context(asyncs.Socket(nng.Protocols.REP0))
            sock1.listen(url)

            sock0 = stack.enter_context(asyncs.Socket(nng.Protocols.REQ0))
            sock0.dial(url)

            with self.subTest((sock0, sock1)):
                do_test(sock0, sock1)

            c0 = stack.enter_context(asyncs.Context(sock0))
            c1 = stack.enter_context(asyncs.Context(sock1))
            with self.subTest((c0, c1)):
                do_test(c0, c1)

    @kernels.with_kernel
    @checking_alive_msg_p
    def test_dialer_start(self):
        with contextlib.ExitStack() as stack:
            url = 'inproc://%s' % uuid.uuid4()

            s1 = stack.enter_context(asyncs.Socket(nng.Protocols.REP0))
            s1.listen(url)

            s0 = stack.enter_context(asyncs.Socket(nng.Protocols.REQ0))
            d = s0.dial(url, create_only=True)
            d.start()

            t0 = tasks.spawn(s0.send(b'hello world'))
            t1 = tasks.spawn(s1.recv())
            kernels.run(timeout=1)
            self.assertTrue(t0.is_completed())
            self.assertTrue(t1.is_completed())
            self.assertEqual(t1.get_result_nonblocking(), b'hello world')

            d = s0.dial('inproc://%s' % uuid.uuid4())
            with self.assertRaises(nng.Errors.ESTATE):
                d.start()

    @kernels.with_kernel
    @checking_alive_msg_p
    def test_message(self):

        def do_test(s0, s1):
            m0 = nng.Message(b'hello world')
            t0 = tasks.spawn(s0.sendmsg(m0))
            t1 = tasks.spawn(s1.recv())
            kernels.run(timeout=1)
            self.assertTrue(t0.is_completed())
            self.assertTrue(t1.is_completed())
            self.assertEqual(t1.get_result_nonblocking(), b'hello world')

            # Ownership is transferred on success.
            self.assertIsNone(m0._msg_p)

        with contextlib.ExitStack() as stack:
            url = 'inproc://%s' % uuid.uuid4()

            sock1 = stack.enter_context(asyncs.Socket(nng.Protocols.REP0))
            sock1.listen(url)

            sock0 = stack.enter_context(asyncs.Socket(nng.Protocols.REQ0))
            sock0.dial(url)

            with self.subTest((sock0, sock1)):
                do_test(sock0, sock1)

            c0 = stack.enter_context(asyncs.Context(sock0))
            c1 = stack.enter_context(asyncs.Context(sock1))
            with self.subTest((c0, c1)):
                do_test(c0, c1)

    @kernels.with_kernel
    @checking_alive_msg_p
    def test_message_error(self):

        def do_test(s0):
            m0 = nng.Message(b'hello world')
            t0 = tasks.spawn(s0.sendmsg(m0))
            t0.cancel()
            kernels.run(timeout=1)
            self.assertTrue(t0.is_completed())
            self.assertIsInstance(
                t0.get_exception_nonblocking(), tasks.Cancelled
            )
            # Ownership was not transferred.
            self.assertIsNotNone(m0._msg_p)

        with contextlib.ExitStack() as stack:
            sock0 = stack.enter_context(asyncs.Socket(nng.Protocols.REQ0))

            with self.subTest(sock0):
                do_test(sock0)

            c0 = stack.enter_context(asyncs.Context(sock0))
            with self.subTest(c0):
                do_test(c0)


if __name__ == '__main__':
    unittest.main()
