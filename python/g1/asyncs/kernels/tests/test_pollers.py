import unittest

import contextlib
import os
import select
import socket
import sys

from g1.asyncs.kernels import pollers


class TestCaseBase(unittest.TestCase):

    @staticmethod
    def _close(fd):
        try:
            os.close(fd)
        except OSError:
            pass

    def setUp(self):
        super().setUp()
        self.exit_stack = contextlib.ExitStack()

    def tearDown(self):
        self.exit_stack.close()
        super().tearDown()

    def open_pipe(self):
        r, w = os.pipe()
        os.set_blocking(r, False)
        os.set_blocking(w, False)
        self.exit_stack.callback(self._close, r)
        self.exit_stack.callback(self._close, w)
        return r, w

    def open_socket(self):
        s0, s1 = socket.socketpair()
        s0.setblocking(False)
        s1.setblocking(False)
        self.exit_stack.callback(s0.close)
        self.exit_stack.callback(s1.close)
        return s0, s1

    def open_file(self):
        r = os.open(os.devnull, os.O_RDONLY)
        w = os.open(os.devnull, os.O_WRONLY)
        self.exit_stack.callback(self._close, r)
        self.exit_stack.callback(self._close, w)
        return r, w


class EpollTest(TestCaseBase):

    def assert_poll(self, pair, expect_can_read, expect_can_write):
        self.assertCountEqual(pair[0], expect_can_read)
        self.assertCountEqual(pair[1], expect_can_write)

    def make_epoll(self):
        epoll = pollers.Epoll()
        self.exit_stack.callback(epoll.close)
        return epoll

    def test_empty_epoll(self):
        epoll = self.make_epoll()
        self.assert_poll(epoll.poll(-1), [], [])

    def test_closed_epoll(self):
        epoll = self.make_epoll()
        epoll.close()
        with self.assertRaisesRegex(AssertionError, r'expect false-value'):
            epoll.notify_open(0)
        with self.assertRaisesRegex(AssertionError, r'expect false-value'):
            epoll.notify_close(0)
        with self.assertRaisesRegex(AssertionError, r'expect false-value'):
            epoll.poll(-1)

    def test_file(self):
        epoll = self.make_epoll()
        r, w = self.open_file()
        # epoll cannot wait for regular file.
        with self.assertRaises(PermissionError):
            epoll.notify_open(r)
        with self.assertRaises(PermissionError):
            epoll.notify_open(w)

    def test_pipe(self):
        epoll = self.make_epoll()
        r, w = self.open_pipe()
        epoll.notify_open(r)
        epoll.notify_open(w)

        self.assert_poll(epoll.poll(-1), [], [w])
        self.assertCountEqual(epoll._closed_fds, [])

        os.write(w, b'hello world')
        self.assert_poll(epoll.poll(-1), [r], [w])
        self.assertCountEqual(epoll._closed_fds, [])

        # Due to EPOLLET, poll returns nothing.
        self.assert_poll(epoll.poll(-1), [], [])

        # epoll does not inform you about closed file descriptors.
        os.close(r)
        os.close(w)
        self.assert_poll(epoll.poll(-1), [], [])
        self.assertCountEqual(epoll._closed_fds, [])

        epoll.notify_close(r)
        epoll.notify_close(w)
        self.assertCountEqual(epoll._closed_fds, [r, w])

        self.assert_poll(epoll.poll(-1), [r, w], [r, w])
        self.assertCountEqual(epoll._closed_fds, [])

        self.assert_poll(epoll.poll(-1), [], [])

    def test_pipe_close_reader(self):
        epoll = self.make_epoll()
        r, w = self.open_pipe()
        epoll.notify_open(r)
        epoll.notify_open(w)

        self.assert_poll(epoll.poll(-1), [], [w])
        self.assertCountEqual(epoll._closed_fds, [])

        os.write(w, b'hello world')
        self.assert_poll(epoll.poll(-1), [r], [w])
        self.assertCountEqual(epoll._closed_fds, [])

        os.close(r)
        # poll returns "extra" fd in the can_read set.
        self.assert_poll(epoll.poll(-1), [w], [w])

    def test_pipe_close_writer(self):
        epoll = self.make_epoll()
        r, w = self.open_pipe()
        epoll.notify_open(r)
        epoll.notify_open(w)

        self.assert_poll(epoll.poll(-1), [], [w])
        self.assertCountEqual(epoll._closed_fds, [])

        os.write(w, b'hello world')
        self.assert_poll(epoll.poll(-1), [r], [w])
        self.assertCountEqual(epoll._closed_fds, [])

        os.close(w)
        # poll returns "extra" fd in the can_write set.
        self.assert_poll(epoll.poll(-1), [r], [r])

    def test_socket(self):
        epoll = self.make_epoll()
        s0, s1 = self.open_socket()
        fd0 = s0.fileno()
        fd1 = s1.fileno()
        epoll.notify_open(fd0)
        epoll.notify_open(fd1)

        self.assert_poll(epoll.poll(-1), [], [fd0, fd1])

        s1.send(b'hello world')
        # Even though s1 is still writeable, due to EPOLLET, poll does
        # not return fd1 in can_write set.
        self.assert_poll(epoll.poll(-1), [fd0], [fd0])

        # Due to EPOLLET, poll returns nothing.
        self.assert_poll(epoll.poll(-1), [], [])

        self.assertEqual(s0.recv(3), b'hel')
        self.assert_poll(epoll.poll(-1), [], [])
        self.assertEqual(s0.recv(8), b'lo world')
        # fd1 re-appears in can_write set after the entire message was
        # consumed.
        self.assert_poll(epoll.poll(-1), [], [fd1])

        # epoll does not inform you about closed file descriptors.
        s0.close()
        s1.close()
        self.assert_poll(epoll.poll(-1), [], [])
        self.assertCountEqual(epoll._closed_fds, [])

        epoll.notify_close(fd0)
        epoll.notify_close(fd1)
        self.assertCountEqual(epoll._closed_fds, [fd0, fd1])

        self.assert_poll(epoll.poll(-1), [fd0, fd1], [fd0, fd1])
        self.assertCountEqual(epoll._closed_fds, [])

    def test_shutdown_socket_rd(self):
        epoll = self.make_epoll()
        s0, s1 = self.open_socket()
        fd0 = s0.fileno()
        fd1 = s1.fileno()
        epoll.notify_open(fd0)
        epoll.notify_open(fd1)

        self.assert_poll(epoll.poll(-1), [], [fd0, fd1])

        s0.shutdown(socket.SHUT_RD)
        self.assert_poll(epoll.poll(-1), [fd0], [fd0, fd1])

        self.assertEqual(s0.recv(64), b'')
        with self.assertRaises(BrokenPipeError):
            s1.send(b'x')

        s0.send(b'hello world')
        self.assertEqual(s1.recv(64), b'hello world')

    def test_shutdown_socket_wr(self):
        epoll = self.make_epoll()
        s0, s1 = self.open_socket()
        fd0 = s0.fileno()
        fd1 = s1.fileno()
        epoll.notify_open(fd0)
        epoll.notify_open(fd1)

        self.assert_poll(epoll.poll(-1), [], [fd0, fd1])

        s0.shutdown(socket.SHUT_WR)
        self.assert_poll(epoll.poll(-1), [fd1], [fd0, fd1])

        with self.assertRaises(BrokenPipeError):
            s0.send(b'x')
        self.assertEqual(s1.recv(64), b'')

        s1.send(b'hello world')
        self.assertEqual(s0.recv(64), b'hello world')

    def test_shutdown_socket_rdwr(self):
        epoll = self.make_epoll()
        s0, s1 = self.open_socket()
        fd0 = s0.fileno()
        fd1 = s1.fileno()
        epoll.notify_open(fd0)
        epoll.notify_open(fd1)

        self.assert_poll(epoll.poll(-1), [], [fd0, fd1])

        s0.shutdown(socket.SHUT_RDWR)
        self.assert_poll(epoll.poll(-1), [fd0, fd1], [fd0, fd1])

        self.assertEqual(s0.recv(64), b'')
        with self.assertRaises(BrokenPipeError):
            s1.send(b'x')

        with self.assertRaises(BrokenPipeError):
            s0.send(b'x')
        self.assertEqual(s1.recv(64), b'')

    def test_close_socket(self):
        epoll = self.make_epoll()
        s0, s1 = self.open_socket()
        fd0 = s0.fileno()
        fd1 = s1.fileno()
        epoll.notify_open(fd0)
        epoll.notify_open(fd1)

        self.assert_poll(epoll.poll(-1), [], [fd0, fd1])

        s0.close()
        self.assert_poll(epoll.poll(-1), [fd1], [fd1])


class SelectEpollTest(TestCaseBase):
    """Ensure that our assumptions about ``select.epoll`` is correct."""

    def open_epoll(self):
        epoll = select.epoll()
        self.exit_stack.callback(epoll.close)
        return epoll

    def test_register_repeated(self):
        epoll = self.open_epoll()
        r, _ = self.open_pipe()
        epoll.register(r, select.EPOLLIN)
        with self.assertRaises(FileExistsError):
            epoll.register(r, select.EPOLLIN)

    def test_register_different_event(self):
        epoll = self.open_epoll()
        r, _ = self.open_pipe()
        epoll.register(r, select.EPOLLIN)
        with self.assertRaises(FileExistsError):
            epoll.register(r, select.EPOLLOUT)

    def test_modify(self):
        epoll = self.open_epoll()
        r, _ = self.open_pipe()
        epoll.register(r, select.EPOLLIN)
        epoll.modify(r, select.EPOLLOUT)

    def test_unregister_repeatedly(self):
        epoll = self.open_epoll()
        r, _ = self.open_pipe()
        epoll.register(r, select.EPOLLIN)
        epoll.unregister(r)
        with self.assertRaises(FileNotFoundError):
            epoll.unregister(r)

    @unittest.skipIf(sys.version_info >= (3, 9), 'changed in python 3.9')
    def test_unregister_after_close_before_python39(self):
        epoll = self.open_epoll()
        r, _ = self.open_pipe()
        epoll.register(r, select.EPOLLIN)
        os.close(r)
        # EBADF is ignored.
        epoll.unregister(r)
        epoll.unregister(r)

    @unittest.skipIf(sys.version_info < (3, 9), 'changed in python 3.9')
    def test_unregister_after_close(self):
        epoll = self.open_epoll()
        r, _ = self.open_pipe()
        epoll.register(r, select.EPOLLIN)
        os.close(r)
        with self.assertRaisesRegex(OSError, r'Bad file descriptor'):
            epoll.unregister(r)

    def test_regular_file(self):
        epoll = self.open_epoll()
        r, w = self.open_file()
        # You cannot register regular file.
        with self.assertRaises(PermissionError):
            epoll.register(r, select.EPOLLIN)
        with self.assertRaises(PermissionError):
            epoll.register(w, select.EPOLLOUT)

    #
    # When a file descriptor is closed, epoll silently drops polling it.
    # You can only detect this from the other end of pipe/socket.  The
    # tests below test this behavior.
    #

    _MASK = select.EPOLLIN | select.EPOLLOUT | select.EPOLLET

    def test_close_pipe(self):
        for mask in [
            self._MASK,
            # Show that you don't get EPOLLRDHUP on pipes.
            self._MASK | select.EPOLLRDHUP,
        ]:
            with self.subTest(mask):
                # Test close reader.
                epoll = self.open_epoll()
                r, w = self.open_pipe()
                epoll.register(r, mask)
                epoll.register(w, mask)
                self.assertEqual(epoll.poll(), [(w, select.EPOLLOUT)])
                os.close(r)
                self.assertEqual(
                    epoll.poll(),
                    [(w, select.EPOLLOUT | select.EPOLLERR)],
                )
                # Nothing in the next poll due to select.EPOLLET.
                self.assertEqual(epoll.poll(timeout=0.01), [])

                # Test close writer.
                epoll = self.open_epoll()
                r, w = self.open_pipe()
                epoll.register(r, mask)
                epoll.register(w, mask)
                self.assertEqual(epoll.poll(), [(w, select.EPOLLOUT)])
                os.close(w)
                self.assertEqual(
                    epoll.poll(),
                    # NOTE: There is no EPOLLIN here!  This makes it
                    # impossible to check only EPOLLIN for readable file
                    # descriptors.
                    [(r, select.EPOLLHUP)],
                )
                # Nothing in the next poll due to select.EPOLLET.
                self.assertEqual(epoll.poll(timeout=0.01), [])

    def test_shutdown_socket(self):
        for mask, how, expect_s0, expect_s1 in [
            (
                self._MASK,
                socket.SHUT_RD,
                select.EPOLLIN | select.EPOLLOUT,
                select.EPOLLOUT,
            ),
            (
                self._MASK,
                socket.SHUT_WR,
                select.EPOLLOUT,
                select.EPOLLIN | select.EPOLLOUT,
            ),
            (
                self._MASK,
                socket.SHUT_RDWR,
                select.EPOLLIN | select.EPOLLOUT | select.EPOLLHUP,
                select.EPOLLIN | select.EPOLLOUT | select.EPOLLHUP,
            ),
            (
                self._MASK | select.EPOLLRDHUP,
                socket.SHUT_RD,
                select.EPOLLIN | select.EPOLLOUT | select.EPOLLRDHUP,
                select.EPOLLOUT,
            ),
            (
                self._MASK | select.EPOLLRDHUP,
                socket.SHUT_WR,
                select.EPOLLOUT,
                select.EPOLLIN | select.EPOLLOUT | select.EPOLLRDHUP,
            ),
            (
                self._MASK | select.EPOLLRDHUP,
                socket.SHUT_RDWR,
                select.EPOLLIN | select.EPOLLOUT | select.EPOLLHUP
                | select.EPOLLRDHUP,
                select.EPOLLIN | select.EPOLLOUT | select.EPOLLHUP
                | select.EPOLLRDHUP,
            ),
        ]:
            with self.subTest((mask, how, expect_s0, expect_s1)):
                epoll = self.open_epoll()
                s0, s1 = self.open_socket()
                epoll.register(s0.fileno(), mask)
                epoll.register(s1.fileno(), mask)
                self.assertEqual(
                    epoll.poll(),
                    [
                        (s0.fileno(), select.EPOLLOUT),
                        (s1.fileno(), select.EPOLLOUT),
                    ],
                )
                s0.shutdown(how)
                self.assertEqual(
                    epoll.poll(),
                    [
                        (s0.fileno(), expect_s0),
                        (s1.fileno(), expect_s1),
                    ],
                )
                # Nothing in the next poll due to select.EPOLLET.
                self.assertEqual(epoll.poll(timeout=0.01), [])

    def test_close_socket(self):
        for mask, expect in [
            (
                self._MASK,
                select.EPOLLIN | select.EPOLLOUT | select.EPOLLHUP,
            ),
            (
                self._MASK | select.EPOLLRDHUP,
                select.EPOLLIN | select.EPOLLOUT | select.EPOLLHUP
                | select.EPOLLRDHUP,
            ),
        ]:
            with self.subTest((mask, expect)):
                epoll = self.open_epoll()
                s0, s1 = self.open_socket()
                epoll.register(s0.fileno(), mask)
                epoll.register(s1.fileno(), mask)
                self.assertEqual(
                    epoll.poll(),
                    [
                        (s0.fileno(), select.EPOLLOUT),
                        (s1.fileno(), select.EPOLLOUT),
                    ],
                )
                s0.close()
                self.assertEqual(epoll.poll(), [(s1.fileno(), expect)])
                # Nothing in the next poll due to select.EPOLLET.
                self.assertEqual(epoll.poll(timeout=0.01), [])


if __name__ == '__main__':
    unittest.main()
