import unittest

from g1.asyncs.kernels import contexts
from g1.asyncs.kernels import errors
from g1.asyncs.kernels import kernels
from g1.asyncs.kernels import locks
from g1.asyncs.kernels import tasks
from g1.asyncs.kernels import utils


async def square(x):
    return x * x


async def raises(message):
    raise Exception(message)


class TaskCompletionQueueTest(unittest.TestCase):

    def setUp(self):
        self.k = kernels.Kernel()
        self.token = contexts.set_kernel(self.k)

    def tearDown(self):
        contexts.KERNEL.reset(self.token)
        self.k.close()

    def test_queue(self):

        tq = utils.TaskCompletionQueue()
        self.assertFalse(tq.is_closed())
        self.assertFalse(tq)
        self.assertEqual(len(tq), 0)

        t1 = self.k.spawn(square(1))
        tq.put(t1)
        self.assertFalse(tq.is_closed())
        self.assertTrue(tq)
        self.assertEqual(len(tq), 1)

        t2 = self.k.spawn(square(1))
        tq.put(t2)
        self.assertFalse(tq.is_closed())
        self.assertTrue(tq)
        self.assertEqual(len(tq), 2)

        tq.close()
        self.assertTrue(tq.is_closed())
        self.assertTrue(tq)
        self.assertEqual(len(tq), 2)

        with self.assertRaises(utils.Closed):
            tq.put(None)

        ts = set()

        ts.add(self.k.run(tq.get, timeout=1))
        self.assertTrue(tq.is_closed())
        self.assertTrue(tq)
        self.assertEqual(len(tq), 1)

        ts.add(self.k.run(tq.get, timeout=1))
        self.assertTrue(tq.is_closed())
        self.assertFalse(tq)
        self.assertEqual(len(tq), 0)

        with self.assertRaises(utils.Closed):
            self.k.run(tq.get)

        self.assertEqual(ts, {t1, t2})

    def test_async_iterator(self):
        tq = utils.TaskCompletionQueue()

        expect = {
            tq.spawn(square(1)),
            tq.spawn(square(2)),
            tq.spawn(square(3)),
        }
        tq.close()

        async def async_iter():
            actual = set()
            async for task in tq:
                actual.add(task)
            return actual

        self.assertEqual(
            self.k.run(async_iter, timeout=1),
            expect,
        )

    def test_not_wait_for(self):
        tq = utils.TaskCompletionQueue()
        event = locks.Event()

        t1 = self.k.spawn(event.wait)
        tq.put(t1, wait_for_completion=False)

        t2 = self.k.spawn(event.wait)
        tq.put(t2, wait_for_completion=False)

        tq.close()
        self.assertTrue(tq.is_closed())
        self.assertTrue(tq)
        self.assertEqual(len(tq), 2)

        self.assertFalse(tq._completed)
        self.assertFalse(tq._uncompleted)
        self.assertEqual(tq._not_wait_for, {t1, t2})
        with self.assertRaises(utils.Closed):
            self.k.run(tq.get, timeout=0)
        self.assertFalse(tq._completed)
        self.assertFalse(tq._uncompleted)
        self.assertEqual(tq._not_wait_for, {t1, t2})

        event.set()
        with self.assertRaises(errors.Timeout):
            self.k.run(timeout=0)
        self.assertEqual(set(tq._completed), {t1, t2})
        self.assertFalse(tq._uncompleted)
        self.assertFalse(tq._not_wait_for)

        ts = set()
        for n in (1, 0):
            ts.add(self.k.run(tq.get, timeout=1))
            self.assertTrue(tq.is_closed())
            self.assertEqual(bool(tq), n != 0)
            self.assertEqual(len(tq), n)
        self.assertFalse(tq)

        with self.assertRaises(utils.Closed):
            self.k.run(tq.get)

        self.assertEqual(ts, {t1, t2})

    def test_spawn(self):
        tq = utils.TaskCompletionQueue()
        tq.close()
        self.assertEqual(self.k.get_all_tasks(), [])
        with self.assertRaises(utils.Closed):
            tq.spawn(square)
        self.assertEqual(self.k.get_all_tasks(), [])

    def test_context_manager(self):
        tq = utils.TaskCompletionQueue()

        t1 = self.k.spawn(square(1))
        tq.put(t1)

        t2 = self.k.spawn(square(2))
        tq.put(t2)

        async def do_with_queue():
            async with tq:
                return 42

        self.assertEqual(self.k.run(do_with_queue, timeout=1), 42)

        self.assertTrue(tq.is_closed())
        self.assertFalse(tq)
        self.assertEqual(len(tq), 0)

        for t, x in [(t1, 1), (t2, 2)]:
            self.assertTrue(t.is_completed())
            self.assertEqual(t.get_result_nonblocking(), x * x)

    def test_context_manager_cancel(self):
        tq = utils.TaskCompletionQueue()

        event = locks.Event()

        t1 = self.k.spawn(event.wait)
        tq.put(t1)

        t2 = self.k.spawn(event.wait)
        tq.put(t2)

        t3 = self.k.spawn(raises('test message'))
        tq.put(t3)

        async def do_with_queue():
            async with tq:
                raise Exception('some error')

        with self.assertRaisesRegex(Exception, r'some error'):
            self.k.run(do_with_queue)

        self.assertTrue(tq.is_closed())
        self.assertFalse(tq)
        self.assertEqual(len(tq), 0)

        for t in (t1, t2):
            self.assertTrue(t.is_completed())
            with self.assertRaises(errors.Cancelled):
                t.get_result_nonblocking()

        self.assertTrue(t3.is_completed())
        with self.assertRaisesRegex(Exception, r'test message'):
            t3.get_result_nonblocking()


class TaskCompletionQueueWithoutKernelTest(unittest.TestCase):

    def test_queue(self):
        with self.assertRaises(LookupError):
            contexts.get_kernel()

        tq = utils.TaskCompletionQueue()
        self.assertFalse(tq.is_closed())
        self.assertFalse(tq)
        self.assertEqual(len(tq), 0)

        task = tasks.Task(square(7))
        tq.put(task)
        self.assertFalse(tq.is_closed())
        self.assertTrue(tq)
        self.assertEqual(len(tq), 1)

        tq.close()
        self.assertTrue(tq.is_closed())
        self.assertTrue(tq)
        self.assertEqual(len(tq), 1)

        self.assertIsNone(task.tick(None, None))


class BytesStreamTest(unittest.TestCase):

    def setUp(self):
        self.s = utils.BytesStream()
        self.k = kernels.Kernel()
        self.token = contexts.set_kernel(self.k)

    def tearDown(self):
        contexts.KERNEL.reset(self.token)
        self.k.close()

    def test_wrong_data_type(self):
        with self.assertRaises(TypeError):
            self.s.nonblocking.write('')

    def test_write_after_close(self):
        stream = self.s.nonblocking
        stream.write(b'hello')
        stream.close()
        with self.assertRaises(AssertionError):
            stream.write(b'')
        self.assertEqual(stream.read(), b'hello')
        self.assertEqual(stream.read(), b'')

    def test_read(self):
        stream = self.s.nonblocking

        self.assert_stream(b'')
        self.assertIsNone(stream.read())

        # Test ``read(size=-1)``.
        self.assertEqual(stream.write(b'hello'), 5)
        self.assert_stream(b'hello')
        self.assertEqual(stream.read(), b'hello')
        self.assert_stream(b'')
        self.assertIsNone(stream.read())
        self.assert_stream(b'')

        # Test ``read(size=0)``.
        self.assertIsNone(stream.read(0))
        self.assertEqual(stream.write(b'world'), 5)
        self.assert_stream(b'world')
        self.assertEqual(stream.read(0), b'')
        self.assert_stream(b'world')
        self.assertEqual(stream.read(0), b'')
        self.assert_stream(b'world')

        # Test size greater than 0.
        self.assertEqual(stream.read(1), b'w')
        self.assert_stream(b'orld')
        self.assertEqual(stream.read(2), b'or')
        self.assert_stream(b'ld')
        self.assertEqual(stream.read(3), b'ld')
        self.assert_stream(b'')
        self.assertIsNone(stream.read(4))
        self.assert_stream(b'')
        self.assertIsNone(stream.read(5))
        self.assert_stream(b'')

        self.assertEqual(stream.write(b'foo'), 3)
        self.assert_stream(b'foo')
        stream.close()
        self.assert_stream(b'foo')
        self.assertEqual(stream.read(1), b'f')
        self.assert_stream(b'oo')
        self.assertEqual(stream.read(0), b'')
        self.assert_stream(b'oo')
        self.assertEqual(stream.read(), b'oo')
        self.assert_stream(b'')

        self.assertEqual(stream.read(), b'')
        self.assert_stream(b'')
        self.assertEqual(stream.read(0), b'')
        self.assert_stream(b'')
        self.assertEqual(stream.read(1), b'')
        self.assert_stream(b'')

    def test_readline_with_size(self):
        stream = self.s.nonblocking

        self.assertEqual(stream.write(b'hello'), 5)

        self.assertEqual(stream.readline(3), b'hel')
        self.assert_stream(b'lo')

        self.assertEqual(stream.write(b'\n'), 1)
        self.assert_stream(b'lo\n')

        self.assertEqual(stream.readline(2), b'lo')
        self.assert_stream(b'\n')

        self.assertEqual(stream.readline(2), b'\n')
        self.assert_stream(b'')

    def test_readline_without_size(self):
        stream = self.s.nonblocking

        self.assert_stream(b'')
        self.assertIsNone(stream.readline())

        self.assertEqual(stream.write(b'hello'), 5)
        self.assert_stream(b'hello')
        self.assertIsNone(stream.readline())
        self.assert_stream(b'hello')

        self.assertEqual(stream.write(b'\n'), 1)
        self.assert_stream(b'hello\n')
        self.assertEqual(stream.readline(), b'hello\n')
        self.assert_stream(b'')
        self.assertIsNone(stream.readline())
        self.assert_stream(b'')

        self.assertEqual(stream.write(b'world'), 5)
        self.assert_stream(b'world')
        self.assertIsNone(stream.readline())
        self.assert_stream(b'world')

        self.assertEqual(stream.write(b'\n'), 1)
        self.assert_stream(b'world\n')
        self.assertEqual(stream.readline(), b'world\n')
        self.assert_stream(b'')
        self.assertIsNone(stream.readline())
        self.assert_stream(b'')

        self.assertEqual(stream.write(b'foo'), 3)
        self.assert_stream(b'foo')
        self.assertIsNone(stream.readline())
        self.assert_stream(b'foo')

        stream.close()
        self.assert_stream(b'foo')
        self.assertEqual(stream.readline(), b'foo')
        self.assert_stream(b'')
        self.assertEqual(stream.readline(), b'')
        self.assert_stream(b'')

    def test_async(self):
        self.assert_stream(b'')

        self.assertEqual(self.k.run(self.s.write(b'hello\n')), 6)
        self.assert_stream(b'hello\n')
        self.assertEqual(self.k.run(self.s.read(3)), b'hel')
        self.assert_stream(b'lo\n')
        self.assertEqual(self.k.run(self.s.readline()), b'lo\n')
        self.assert_stream(b'')

        t = self.k.spawn(self.s.read(0))
        with self.assertRaises(errors.Timeout):
            self.k.run(timeout=0)
        self.assert_stream(b'')

        for _ in range(3):
            self.k.run(self.s.write(b''))
            with self.assertRaises(errors.Timeout):
                self.k.run(timeout=0)
            self.assert_stream(b'')

        self.k.run(self.s.write(b'world'))
        self.k.run(self.s.write(b''))
        self.k.run(self.s.write(b''))
        self.assert_stream(b'world')

        self.k.run()
        self.assert_stream(b'world')
        self.assertEqual(t.get_result_nonblocking(), b'')

        self.k.run(self.s.close())
        self.assert_stream(b'world')

        self.assertEqual(self.k.run(self.s.read()), b'world')
        self.assert_stream(b'')

        self.assertEqual(self.k.run(self.s.read()), b'')
        self.assertEqual(self.k.run(self.s.readline()), b'')
        self.assert_stream(b'')

    def test_async_iterator(self):

        lines = []

        async def do_iter():
            async for line in self.s:
                lines.append(line)

        t = self.k.spawn(do_iter)
        self.assertFalse(t.is_completed())
        self.assertEqual(lines, [])
        self.assert_stream(b'')

        with self.assertRaises(errors.Timeout):
            self.k.run(timeout=0)
        self.assertFalse(t.is_completed())
        self.assertEqual(lines, [])
        self.assert_stream(b'')

        self.k.run(self.s.write(b'hello'))
        self.assertFalse(t.is_completed())
        self.assertEqual(lines, [])
        self.assert_stream(b'hello')

        self.k.run(self.s.write(b'\n'))
        self.assertFalse(t.is_completed())

        with self.assertRaises(errors.Timeout):
            self.k.run(timeout=0)
        self.assertFalse(t.is_completed())
        self.assertEqual(lines, [b'hello\n'])
        self.assert_stream(b'')

        self.k.run(self.s.write(b'world\n'))
        self.k.run(self.s.write(b'foo'))

        with self.assertRaises(errors.Timeout):
            self.k.run(timeout=0)

        self.s.close()
        self.k.run(timeout=1)

        self.assertTrue(t.is_completed())
        self.assertEqual(lines, [b'hello\n', b'world\n', b'foo'])
        self.assert_stream(b'')

    def test_async_readlines_with_hint(self):

        t = self.k.spawn(self.s.readlines(12))
        self.assertFalse(t.is_completed())

        for piece in (b'hello', b'\n', b'world', b'\n', b'foo\n', b'bar\n'):
            self.assertEqual(self.k.run(self.s.write(piece)), len(piece))

        self.assert_stream(b'foo\nbar\n')
        self.assertEqual(t.get_result_nonblocking(), [b'hello\n', b'world\n'])

    def test_async_readlines_without_hint(self):

        t = self.k.spawn(self.s.readlines())
        self.assertFalse(t.is_completed())

        for piece in (b'hello', b'\n', b'world\n', b'foo'):
            self.assertEqual(self.k.run(self.s.write(piece)), len(piece))
            self.assertFalse(t.is_completed())

        with self.assertRaises(errors.Timeout):
            self.k.run(timeout=0)
        self.assertFalse(t.is_completed())
        self.assert_stream(b'foo')

        with self.assertRaises(errors.Timeout):
            self.k.run(timeout=0)

        self.s.close()
        self.k.run(timeout=1)

        self.assert_stream(b'')
        self.assertEqual(
            t.get_result_nonblocking(),
            [b'hello\n', b'world\n', b'foo'],
        )

    def assert_stream(self, expect):
        self.assertEqual(self.s._buffer.getvalue(), expect)
        self.assertEqual(self.s._buffer.tell(), len(expect))


class StringStreamTest(unittest.TestCase):

    def setUp(self):
        self.s = utils.StringStream()
        self.k = kernels.Kernel()
        self.token = contexts.set_kernel(self.k)

    def tearDown(self):
        contexts.KERNEL.reset(self.token)
        self.k.close()

    def test_wrong_data_type(self):
        with self.assertRaises(TypeError):
            self.s.nonblocking.write(b'')


if __name__ == '__main__':
    unittest.main()
