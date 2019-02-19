import unittest

import os
import socket

from g1.asyncs.bases import adapters
from g1.asyncs.kernels import contexts
from g1.asyncs.kernels import errors
from g1.asyncs.kernels import kernels

try:
    from g1.threads import futures
except ImportError:
    futures = None


class FileAdapterTest(unittest.TestCase):

    def setUp(self):
        self.k = kernels.Kernel()
        self.token = contexts.set_kernel(self.k)
        r, w = os.pipe()
        self.r = adapters.FileAdapter(os.fdopen(r, 'rb'))
        self.w = adapters.FileAdapter(os.fdopen(w, 'wb'))

    def tearDown(self):
        contexts.KERNEL.reset(self.token)
        self.k.close()
        self.r.target.close()
        self.w.target.close()

    def assert_stats(self, **expect):
        actual = self.k.get_stats()._asdict()
        # Default ``expect`` entries to 0.
        for name in actual:
            if name not in expect:
                expect[name] = 0
        self.assertEqual(actual, expect)

    def test_pipe(self):

        num_chunks = 10
        # The 65537 of chunk size seems to be a magic number that is
        # larger than pipe's internal buffer size.
        chunk_size = 65536 + 1

        async def write():
            num_written = 0
            for i in range(num_chunks):
                chunk = (b'%x' % (i + 1)) * chunk_size
                while chunk:
                    num_bytes = await self.w.write(chunk)
                    self.assertGreater(num_bytes, 0)
                    chunk = chunk[num_bytes:]
                    num_written += num_bytes
            await self.w.flush()
            self.w.close()
            self.w.close()  # Safe to close repeatedly.
            return num_written

        async def read():
            pieces = []
            while True:
                piece = await self.r.read()
                if not piece:
                    break
                pieces.append(piece)
            self.r.close()
            self.r.close()  # Safe to close repeatedly.
            return b''.join(pieces)

        reader_task = self.k.spawn(read)
        writer_task = self.k.spawn(write)
        self.assertFalse(reader_task.is_completed())
        self.assertFalse(writer_task.is_completed())

        self.k.run(timeout=1)

        self.assertTrue(reader_task.is_completed())
        self.assertTrue(writer_task.is_completed())

        expect_data = b''.join((b'%x' % (i + 1)) * chunk_size
                               for i in range(num_chunks))
        self.assertEqual(reader_task.get_result_nonblocking(), expect_data)
        self.assertEqual(
            writer_task.get_result_nonblocking(), len(expect_data)
        )

    def test_close_read_pipe(self):

        # This task is blocked before close.
        reader_task = self.k.spawn(self.r.read)
        with self.assertRaises(errors.Timeout):
            self.k.run(timeout=0)
        self.assert_stats(num_ticks=1, num_tasks=1, num_poll=1)

        self.r.close()
        self.k.run(timeout=1)

        self.assertTrue(reader_task.is_completed())
        with self.assertRaisesRegex(ValueError, r'read of closed file'):
            reader_task.get_result_nonblocking()

        # This task accesses the file after close.
        reader_task = self.k.spawn(self.r.read)
        self.k.run(timeout=1)
        with self.assertRaisesRegex(ValueError, r'read of closed file'):
            reader_task.get_result_nonblocking()

    def test_close_write_pipe(self):

        async def writer_blocked():
            chunk = b'\x00' * 65537
            while True:
                await self.w.write(chunk)

        # This task is blocked before close.
        writer_task = self.k.spawn(writer_blocked)
        with self.assertRaises(errors.Timeout):
            self.k.run(timeout=0)
        self.assert_stats(num_ticks=1, num_tasks=1, num_poll=1)

        self.w.close()
        self.k.run(timeout=1)

        self.assertTrue(writer_task.is_completed())
        with self.assertRaisesRegex(ValueError, r'write to closed file'):
            writer_task.get_result_nonblocking()

        # This task accesses the file after close.
        writer_task = self.k.spawn(writer_blocked)
        self.k.run(timeout=1)
        self.assertTrue(writer_task.is_completed())
        with self.assertRaisesRegex(ValueError, r'write to closed file'):
            writer_task.get_result_nonblocking()

    def test_close_blocked(self):

        num_bytes = 65537
        buffer = bytes(num_bytes)

        # Let's check that ``close`` raises.
        r, w = os.pipe()
        os.set_blocking(r, False)
        os.set_blocking(w, False)
        rr = os.fdopen(r, 'rb')
        ww = os.fdopen(w, 'wb')
        ww.write(buffer)
        with self.assertRaises(BlockingIOError):
            ww.close()
        rr.close()

        # But adapter's ``close`` won't raise.
        async def writer():
            await self.w.write(buffer)
            self.w.close()

        task = self.k.spawn(writer)
        with self.assertLogs(adapters.__name__) as cm:
            self.k.run(timeout=1)
        self.assertRegex(
            cm.output[0],
            r'close error',
        )
        self.assertRegex(
            cm.output[-1],
            (
                r'BlockingIOError: '
                r'\[Errno 11\] write could not complete without blocking'
            ),
        )

        self.assertTrue(task.is_completed())
        self.assertIsNone(task.get_exception_nonblocking())

        # Not all of the data have been flushed out.
        self.assertLess(len(self.r.target.read()), num_bytes)


class SocketAdapterTest(unittest.TestCase):

    def setUp(self):
        self.k = kernels.Kernel()
        self.token = contexts.set_kernel(self.k)
        s0, s1 = socket.socketpair()
        self.s0 = adapters.SocketAdapter(s0)
        self.s1 = adapters.SocketAdapter(s1)

    def tearDown(self):
        contexts.KERNEL.reset(self.token)
        self.k.close()
        self.s0.target.close()
        self.s1.target.close()

    def test_socket_send(self):

        async def send(num_chunks, chunk_size):
            num_sent = 0
            for i in range(num_chunks):
                chunk = (b'%x' % (i + 1)) * chunk_size
                while chunk:
                    num_bytes = await self.s0.send(chunk)
                    self.assertGreater(num_bytes, 0)
                    chunk = chunk[num_bytes:]
                    num_sent += num_bytes
            self.s0.close()
            return num_sent

        self.do_test_socket(send)

    def test_socket_sendmsg(self):

        async def sendmsg(num_chunks, chunk_size):
            chunks = [(b'%x' % (i + 1)) * chunk_size
                      for i in range(num_chunks)]
            num_sent = 0
            while chunks:
                num_bytes = await self.s0.sendmsg(chunks)
                self.assertGreater(num_bytes, 0)
                num_sent += num_bytes
                while chunks:
                    if len(chunks[0]) <= num_bytes:
                        num_bytes -= len(chunks.pop(0))
                    else:
                        chunks[0] = chunks[0][num_bytes:]
                        break
            self.s0.close()
            return num_sent

        self.do_test_socket(sendmsg)

    def do_test_socket(self, send):

        num_chunks = 10
        chunk_size = 65536

        async def recv():
            pieces = []
            while True:
                piece = await self.s1.recv(4096)
                if not piece:
                    break
                pieces.append(piece)
            self.s1.close()
            return b''.join(pieces)

        sender = self.k.spawn(send(num_chunks, chunk_size))
        receiver = self.k.spawn(recv)
        self.assertFalse(sender.is_completed())
        self.assertFalse(receiver.is_completed())

        self.k.run(timeout=1)

        self.assertTrue(sender.is_completed())
        self.assertTrue(receiver.is_completed())

        expect_data = b''.join((b'%x' % (i + 1)) * chunk_size
                               for i in range(num_chunks))
        self.assertEqual(receiver.get_result_nonblocking(), expect_data)
        self.assertEqual(sender.get_result_nonblocking(), len(expect_data))

    def test_close(self):

        # Access before socket is closed.
        task0 = self.k.spawn(self.s0.recv(1024))
        with self.assertRaises(errors.Timeout):
            self.k.run(timeout=0)
        self.assertEqual(self.k.get_stats().num_poll, 1)

        self.s0.close()

        # Access after socket is closed.
        task1 = self.k.spawn(self.s0.recv(1024))
        task2 = self.k.spawn(self.s0.send(b'\x00'))
        self.k.run(timeout=1)

        self.assertTrue(task0.is_completed())
        self.assertTrue(task1.is_completed())
        self.assertTrue(task2.is_completed())
        with self.assertRaisesRegex(OSError, r'Bad file descriptor'):
            task0.get_result_nonblocking()
        with self.assertRaisesRegex(OSError, r'Bad file descriptor'):
            task1.get_result_nonblocking()
        with self.assertRaisesRegex(OSError, r'Bad file descriptor'):
            task2.get_result_nonblocking()


@unittest.skipIf(futures is None, 'g1.threads.futures unavailable')
class FutureAdapterTest(unittest.TestCase):

    def setUp(self):
        self.k = kernels.Kernel()
        self.token = contexts.set_kernel(self.k)

    def tearDown(self):
        contexts.KERNEL.reset(self.token)
        self.k.close()

    def test_future(self):
        f = adapters.FutureAdapter(futures.Future())

        task = self.k.spawn(f.get_result())
        self.assertFalse(task.is_completed())

        with self.assertRaises(errors.Timeout):
            self.k.run(timeout=0)
        self.assertFalse(task.is_completed())

        f.set_result(42)
        self.assertFalse(task.is_completed())

        self.k.run()

        self.assertTrue(task.is_completed())
        self.assertEqual(task.get_result_nonblocking(), 42)

    def test_completed_future(self):
        f = adapters.FutureAdapter(futures.Future())
        f.set_result(42)

        task = self.k.spawn(f.get_result())
        self.assertFalse(task.is_completed())

        self.k.run()

        self.assertTrue(task.is_completed())
        self.assertEqual(task.get_result_nonblocking(), 42)

    def test_system_exit(self):
        f = adapters.FutureAdapter(futures.Future())
        f.set_exception(SystemExit())

        task = self.k.spawn(f.get_result())
        self.assertFalse(task.is_completed())

        self.k.run()

        self.assertTrue(task.is_completed())
        with self.assertRaises(SystemExit):
            task.get_result_nonblocking()


if __name__ == '__main__':
    unittest.main()
