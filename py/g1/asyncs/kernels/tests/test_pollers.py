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
            {(r, select.EPOLLHUP), (w, select.EPOLLHUP)},
        )

        epoll.unregister(r)
        epoll.unregister(w)
        with self.assertRaisesRegex(AssertionError, r'expect non-empty'):
            epoll.poll(-1)

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
            {(r, select.EPOLLHUP), (w, select.EPOLLHUP)},
        )

        epoll.unregister(r)
        epoll.unregister(w)
        with self.assertRaisesRegex(AssertionError, r'expect non-empty'):
            epoll.poll(-1)

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
            [(r, select.EPOLLIN | select.EPOLLHUP | select.EPOLLRDHUP)],
        )
        self.assertEqual(s0.recv(32), b'hello world')
        self.assertEqual(s0.recv(32), b'')
        self.assertEqual(
            epoll.poll(-1),
            [(r, select.EPOLLIN | select.EPOLLHUP | select.EPOLLRDHUP)],
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


if __name__ == '__main__':
    unittest.main()
