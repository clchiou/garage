import unittest

import os
import select
import socket

from g1.asyncs.kernels import pollers


class EpollTest(unittest.TestCase):

    def test_file(self):
        epoll = pollers.Epoll()
        r = os.open(os.devnull, os.O_RDONLY)
        w = os.open(os.devnull, os.O_WRONLY)
        # epoll cannot wait for regular file.
        with self.assertRaises(PermissionError):
            epoll.register(r, epoll.READ)
        with self.assertRaises(PermissionError):
            epoll.register(w, epoll.WRITE)
        os.close(r)
        os.close(w)

    def test_pipe(self):
        epoll = pollers.Epoll()
        r, w = os.pipe()
        os.set_blocking(r, False)
        os.set_blocking(w, False)
        epoll.register(r, epoll.READ)
        epoll.register(w, epoll.WRITE)

        self.assertEqual(epoll.poll(-1), [(w, select.EPOLLOUT)])

        os.write(w, b'hello world')
        self.assertEqual(
            set(epoll.poll(-1)),
            {(r, select.EPOLLIN), (w, select.EPOLLOUT)},
        )

        # epoll does not inform you about closed file descriptors.
        os.close(r)
        os.close(w)
        self.assertEqual(epoll.poll(-1), [])

        epoll.close_fd(r)
        epoll.close_fd(w)
        self.assertEqual(
            set(epoll.poll(-1)),
            {
                (r, select.EPOLLIN | select.EPOLLHUP),
                (w, select.EPOLLOUT | select.EPOLLHUP),
            },
        )

        with self.assertRaisesRegex(AssertionError, r'expect non-empty'):
            epoll.poll(-1)

        self.assertEqual(epoll._epoll.poll(timeout=0), [])

    def test_pipe_reader_epollhup(self):
        epoll = pollers.Epoll()
        r, w = os.pipe()
        os.set_blocking(r, False)
        os.set_blocking(w, False)
        epoll.register(r, epoll.READ)
        epoll.register(w, epoll.WRITE)

        self.assertEqual(epoll.poll(-1), [(w, select.EPOLLOUT)])

        os.write(w, b'hello world')
        os.close(w)
        self.assertEqual(
            epoll.poll(-1),
            [(r, select.EPOLLIN | select.EPOLLHUP)],
        )
        self.assertEqual(os.read(r, 32), b'hello world')
        self.assertEqual(os.read(r, 32), b'')
        self.assertEqual(
            epoll.poll(-1),
            [(r, select.EPOLLHUP)],
        )
        self.assertEqual(os.read(r, 32), b'')

        os.close(r)
        self.assertEqual(epoll.poll(-1), [])

    def test_pipe_writer_epollhup(self):
        epoll = pollers.Epoll()
        r, w = os.pipe()
        os.set_blocking(r, False)
        os.set_blocking(w, False)
        epoll.register(r, epoll.READ)
        epoll.register(w, epoll.WRITE)

        self.assertEqual(epoll.poll(-1), [(w, select.EPOLLOUT)])

        os.close(r)
        self.assertEqual(
            epoll.poll(-1),
            [(w, select.EPOLLOUT | select.EPOLLERR)],
        )

    def test_socket(self):
        epoll = pollers.Epoll()
        s0, s1 = socket.socketpair()
        s0.setblocking(False)
        s1.setblocking(False)
        r = s0.fileno()
        w = s1.fileno()
        epoll.register(r, epoll.READ)
        epoll.register(w, epoll.WRITE)

        self.assertEqual(epoll.poll(-1), [(w, select.EPOLLOUT)])

        s1.send(b'hello world')
        self.assertEqual(
            set(epoll.poll(-1)),
            {(r, select.EPOLLIN), (w, select.EPOLLOUT)},
        )

        # epoll does not inform you about closed file descriptors.
        s0.close()
        s1.close()
        self.assertEqual(epoll.poll(-1), [])

        epoll.close_fd(r)
        epoll.close_fd(w)
        self.assertEqual(
            set(epoll.poll(-1)),
            {
                (r, select.EPOLLIN | select.EPOLLHUP),
                (w, select.EPOLLOUT | select.EPOLLHUP),
            },
        )

        with self.assertRaisesRegex(AssertionError, r'expect non-empty'):
            epoll.poll(-1)

    def test_socket_rw(self):
        epoll = pollers.Epoll()
        s0, s1 = socket.socketpair()

        s0.setblocking(False)
        r = s0.fileno()

        s1.send(b'hello world')

        epoll.register(r, epoll.READ)
        self.assertEqual(
            set(epoll.poll(-1)),
            {(r, select.EPOLLIN)},
        )
        self.assertEqual(epoll._events, {r: epoll.READ})

        epoll.register(r, epoll.WRITE)
        self.assertEqual(
            set(epoll.poll(-1)),
            {(r, select.EPOLLIN | select.EPOLLOUT)},
        )
        self.assertEqual(epoll._events, {r: epoll.READ | epoll.WRITE})

        epoll.close_fd(r)
        self.assertEqual(epoll._events, {})

        s0.close()
        s1.close()

    def test_socket_reader_epollhup(self):
        epoll = pollers.Epoll()
        s0, s1 = socket.socketpair()
        s0.setblocking(False)
        s1.setblocking(False)
        r = s0.fileno()
        epoll.register(r, epoll.READ)

        self.assertEqual(epoll.poll(-1), [])

        s1.send(b'hello world')
        s1.close()
        self.assertEqual(
            epoll.poll(-1),
            [(r, select.EPOLLIN | select.EPOLLHUP)],
        )
        self.assertEqual(s0.recv(32), b'hello world')
        self.assertEqual(s0.recv(32), b'')
        self.assertEqual(
            epoll.poll(-1),
            [(r, select.EPOLLIN | select.EPOLLHUP)],
        )
        self.assertEqual(s0.recv(32), b'')

        s0.close()
        self.assertEqual(epoll.poll(-1), [])

    def test_socket_writer_epollhup(self):
        epoll = pollers.Epoll()
        s0, s1 = socket.socketpair()
        s0.setblocking(False)
        s1.setblocking(False)
        w = s1.fileno()
        epoll.register(w, epoll.WRITE)

        self.assertEqual(epoll.poll(-1), [(w, select.EPOLLOUT)])

        s0.close()
        self.assertEqual(
            epoll.poll(-1),
            [(w, select.EPOLLOUT | select.EPOLLHUP)],
        )

        s1.close()
        self.assertEqual(epoll.poll(-1), [])

    def test_epoll_closed(self):
        epoll = pollers.Epoll()
        epoll.close()
        with self.assertRaisesRegex(AssertionError, r'expect false-value'):
            epoll.poll(-1)

    def test_empty_fds(self):
        epoll = pollers.Epoll()
        with self.assertRaisesRegex(AssertionError, r'expect non-empty'):
            epoll.poll(-1)


class SelectEpollTest(unittest.TestCase):
    """Ensure that our assumptions about ``select.epoll`` is correct."""

    def setUp(self):
        self.epoll = select.epoll()
        self.r, self.w = os.pipe()
        os.set_blocking(self.r, False)
        os.set_blocking(self.w, False)

    def tearDown(self):
        for fd in (self.r, self.w):
            try:
                os.close(fd)
            except OSError:
                pass
        self.epoll.close()

    def test_register_repeated(self):
        self.epoll.register(self.r, select.EPOLLIN)
        with self.assertRaises(FileExistsError):
            self.epoll.register(self.r, select.EPOLLIN)

    def test_register_different_event(self):
        self.epoll.register(self.r, select.EPOLLIN)
        with self.assertRaises(FileExistsError):
            self.epoll.register(self.r, select.EPOLLOUT)

    def test_modify(self):
        self.epoll.register(self.r, select.EPOLLIN)
        self.epoll.modify(self.r, select.EPOLLOUT)

    def test_unregister_repeatedly(self):
        self.epoll.register(self.r, select.EPOLLIN)
        self.epoll.unregister(self.r)
        with self.assertRaises(FileNotFoundError):
            self.epoll.unregister(self.r)

    def test_regular_file(self):
        r = os.open(os.devnull, os.O_RDONLY)
        w = os.open(os.devnull, os.O_WRONLY)
        try:
            # You cannot register regular file.
            with self.assertRaises(PermissionError):
                self.epoll.register(r, select.EPOLLIN)
            with self.assertRaises(PermissionError):
                self.epoll.register(w, select.EPOLLOUT)
        finally:
            os.close(r)
            os.close(w)

    def test_close_pipe(self):
        self.epoll.register(self.r, select.EPOLLIN)
        self.epoll.register(self.w, select.EPOLLOUT)
        self.assertEqual(self.epoll.poll(), [(self.w, select.EPOLLOUT)])
        os.close(self.w)
        # ``epoll`` does not inform you that ``self.w`` is closed; you
        # only get informed on ``self.r``.
        self.assertEqual(self.epoll.poll(), [(self.r, select.EPOLLHUP)])

    def test_close_socket(self):
        s0, s1 = socket.socketpair()
        s0.setblocking(False)
        s1.setblocking(False)
        self.epoll.register(s0.fileno(), select.EPOLLIN)
        self.epoll.register(s1.fileno(), select.EPOLLOUT)
        self.assertEqual(
            self.epoll.poll(timeout=0),
            [(s1.fileno(), select.EPOLLOUT)],
        )
        s1.close()
        try:
            # ``epoll`` does not inform you that ``s1`` is closed; you
            # only get informed on ``s0``.
            self.assertEqual(
                self.epoll.poll(timeout=0),
                [(s0.fileno(), select.EPOLLIN | select.EPOLLHUP)],
            )
            self.epoll.modify(s0.fileno(), select.EPOLLOUT)
            self.assertEqual(
                self.epoll.poll(timeout=0),
                [(s0.fileno(), select.EPOLLOUT | select.EPOLLHUP)],
            )
            self.epoll.modify(s0.fileno(), select.EPOLLIN | select.EPOLLOUT)
            self.assertEqual(
                self.epoll.poll(timeout=0),
                [(
                    s0.fileno(),
                    select.EPOLLIN | select.EPOLLOUT | select.EPOLLHUP,
                )],
            )
        finally:
            s0.close()
        # ``epoll`` does not inform you that ``s0`` is closed.
        self.assertEqual(self.epoll.poll(timeout=0), [])


if __name__ == '__main__':
    unittest.main()
