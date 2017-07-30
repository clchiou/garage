import unittest

import asyncio
import concurrent.futures.thread
import threading
import time

import curio

from nanomsg.asyncio import Socket as AsyncioSocket
from nanomsg.curio import Socket as CurioSocket
import nanomsg as nn

import tests.utils


class SocketTest(unittest.TestCase):
    """
    Test when a thread/coroutine is blocked in send/recv, closing the
    socket may unblock it.
    """

    @staticmethod
    def zombify(socket):
        """Close a socket but retain its file descriptor.

        This makes a "zombie" socket, which should trigger EBADF on any
        operation.
        """
        fd = socket.fd
        socket.close()
        socket.fd = fd

    def test_send_ebadf(self):
        url = 'inproc://test'
        socket = nn.Socket(protocol=nn.NN_REQ)
        socket.connect(url)
        self.zombify(socket)
        try:
            with self.assertRaises(nn.EBADF):
                socket.send(b'')
        finally:
            socket.fd = None

    def test_recv_ebadf(self):
        url = 'inproc://test'
        socket = nn.Socket(protocol=nn.NN_REP)
        socket.bind(url)
        self.zombify(socket)
        try:
            with self.assertRaises(nn.EBADF):
                socket.recv()
        finally:
            socket.fd = None

    def test_options_ebadf(self):
        url = 'inproc://test'
        socket = nn.Socket(protocol=nn.NN_REQ)
        socket.connect(url)
        self.zombify(socket)
        try:
            with self.assertRaises(nn.EBADF):
                socket.options.nn_sndfd
            with self.assertRaises(nn.EBADF):
                socket.options.nn_rcvfd
        finally:
            socket.fd = None

    def test_blocked_thread_recv_ebadf(self):
        """
        Unlike test_recv_ebadf, which closes the socket before recv,
        this one tries to call close while another thread is blocked in
        recv.  Unfortunately due to race condition, this test is not
        sound, and we just do the best we can.
        """

        url = 'inproc://test'
        socket = nn.Socket(protocol=nn.NN_REP)
        socket.bind(url)

        executor = concurrent.futures.thread.ThreadPoolExecutor()
        recv_future = executor.submit(socket.recv)

        # This does not solve the race condition, but if we are lucky,
        # the thread above is blocked in recv while we are sleeping...
        time.sleep(0.1)

        self.zombify(socket)
        try:
            with self.assertRaises(nn.EBADF):
                recv_future.result()
        finally:
            socket.fd = None

    def test_blocked_asyncio_recv_ebadf(self):
        """Like test_blocked_thread_recv_ebadf but for asyncio task."""

        url = 'inproc://test'
        socket = AsyncioSocket(protocol=nn.NN_REP)
        socket.bind(url)

        rcvfd = socket.options.nn_rcvfd

        async def zombify():
            # If we are lucky, this may prevent race condition...
            await asyncio.sleep(0.1)
            self.zombify(socket)

        try:
            recv_future = asyncio.ensure_future(socket.recv())
            zombify_future = asyncio.ensure_future(zombify())
            wait_all = asyncio.wait([recv_future, zombify_future])

            loop = asyncio.get_event_loop()
            loop.run_until_complete(wait_all)

            with self.assertRaises(nn.EBADF):
                recv_future.result()

            zombify_future.result()

        finally:
            socket.fd = None

    def test_blocked_curio_recv_ebadf(self):
        """Like test_blocked_thread_recv_ebadf but for curio task."""

        url = 'inproc://test'
        socket = CurioSocket(protocol=nn.NN_REP)
        socket.bind(url)

        rcvfd = socket.options.nn_rcvfd

        async def recv():
            with self.assertRaises(nn.EBADF):
                await socket.recv()

        async def zombify():
            # If we are lucky, this may prevent race condition...
            await curio.sleep(0.1)
            self.zombify(socket)

        async def run():
            recv_task = await curio.spawn(recv())
            zombify_task = await curio.spawn(zombify())
            await recv_task.join()
            await zombify_task.join()

        try:
            curio.run(run())

        finally:
            socket.fd = None


if __name__ == '__main__':
    unittest.main()
