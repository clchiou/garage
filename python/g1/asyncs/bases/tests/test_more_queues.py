import unittest

from g1.asyncs import kernels
from g1.asyncs.bases import more_queues
from g1.asyncs.bases import queues
from g1.asyncs.bases import tasks


class MultiplexTest(unittest.TestCase):

    @kernels.with_kernel
    def test_select(self):
        q1 = queues.Queue()
        q1.put_nonblocking('x')
        q1.put_nonblocking('y')
        q1.close()
        q2 = queues.Queue()
        q2.put_nonblocking('a')
        q2.put_nonblocking('b')
        q2.put_nonblocking('c')
        q2.put_nonblocking('d')
        q2.close()
        generator = more_queues.select([q1, q2])

        async def anext():
            return await generator.__anext__()  # pylint: disable=no-member

        for item in 'xaybcd':
            self.assertEqual(kernels.run(anext(), timeout=0.01), item)
        with self.assertRaises(StopAsyncIteration):
            kernels.run(anext(), timeout=0.01)

    @kernels.with_kernel
    def test_multiplex(self):
        q1 = queues.Queue()
        q2 = queues.Queue()
        q_out = queues.Queue()
        multiplexer_task = tasks.spawn(more_queues.multiplex([q1, q2], q_out))

        q1.put_nonblocking('x')
        with self.assertRaises(kernels.KernelTimeout):
            kernels.run(timeout=0.01)
        self.assertEqual(get_many(q_out), ['x'])

        q2.put_nonblocking('a')
        q1.put_nonblocking('y')
        q2.put_nonblocking('b')
        with self.assertRaises(kernels.KernelTimeout):
            kernels.run(timeout=0.01)
        # Hmmm... The order of q_out items depends on the internal
        # implementation of multiplex.  I am not sure whether this is a
        # good test case.
        self.assertEqual(get_many(q_out), ['a', 'y', 'b'])

        q2.put_nonblocking('c')
        q2.put_nonblocking('d')
        q2.put_nonblocking('e')
        with self.assertRaises(kernels.KernelTimeout):
            kernels.run(timeout=0.01)
        self.assertEqual(get_many(q_out), ['c', 'd', 'e'])

        q2.close()
        q1.put_nonblocking('z')
        with self.assertRaises(kernels.KernelTimeout):
            kernels.run(timeout=0.01)
        self.assertEqual(get_many(q_out), ['z'])
        self.assertFalse(multiplexer_task.is_completed())

        q1.put_nonblocking('w')
        q1.close()
        kernels.run(timeout=0.01)
        self.assertEqual(get_many(q_out), ['w'])
        self.assertTrue(q_out.is_closed())
        self.assertTrue(multiplexer_task.is_completed())
        self.assertIsNone(multiplexer_task.get_result_nonblocking())

    @kernels.with_kernel
    def test_round_robin(self):
        q1 = queues.Queue()
        q1.put_nonblocking('x')
        q1.put_nonblocking('y')
        q1.put_nonblocking('z')
        q1.close()
        q2 = queues.Queue()
        q2.put_nonblocking('a')
        q2.put_nonblocking('b')
        q2.put_nonblocking('c')
        q2.put_nonblocking('d')
        q2.put_nonblocking('e')
        q2.put_nonblocking('f')
        q2.close()
        q_out = queues.Queue()
        kernels.run(more_queues.multiplex([q1, q2], q_out), timeout=0.01)
        self.assertTrue(q_out.is_closed())
        self.assertEqual(
            q_out.close(graceful=False),
            ['x', 'a', 'y', 'b', 'z', 'c', 'd', 'e', 'f'],
        )

    @kernels.with_kernel
    def test_cancel(self):
        q1 = queues.Queue()
        q2 = queues.Queue()
        q_out = queues.Queue(1)
        multiplexer_task = tasks.spawn(more_queues.multiplex([q1, q2], q_out))
        q1.put_nonblocking('x')
        q1.put_nonblocking('y')
        q2.put_nonblocking('a')
        q2.put_nonblocking('b')
        with self.assertRaises(kernels.KernelTimeout):
            kernels.run(timeout=0.01)
        multiplexer_task.cancel()
        kernels.run(timeout=0.01)
        self.assertTrue(multiplexer_task.is_completed())
        self.assertIsInstance(
            multiplexer_task.get_exception_nonblocking(), tasks.Cancelled
        )
        self.assertTrue(q_out.is_closed())
        # No input item is lost.
        self.assertEqual(get_many(q1), ['y'])
        self.assertEqual(get_many(q2), ['a', 'b'])
        self.assertEqual(get_many(q_out), ['x'])

    @kernels.with_kernel
    def test_bounded_output(self):
        q1 = queues.Queue()
        q_out = queues.Queue(1)
        multiplexer_task = tasks.spawn(more_queues.multiplex([q1], q_out))
        q1.put_nonblocking('x')
        q1.put_nonblocking('y')
        with self.assertRaises(kernels.KernelTimeout):
            kernels.run(timeout=0.01)
        self.assertEqual(get_many(q_out), ['x'])
        with self.assertRaises(kernels.KernelTimeout):
            kernels.run(timeout=0.01)
        self.assertEqual(get_many(q_out), ['y'])
        q1.close()
        kernels.run(timeout=0.01)
        self.assertTrue(multiplexer_task.is_completed())
        self.assertIsNone(multiplexer_task.get_result_nonblocking())

    @kernels.with_kernel
    def test_closed_output(self):
        q1 = queues.Queue()
        q_out = queues.Queue()
        multiplexer_task = tasks.spawn(more_queues.multiplex([q1], q_out))
        with self.assertRaises(kernels.KernelTimeout):
            kernels.run(timeout=0.01)
        q1.put_nonblocking('x')
        q_out.close()
        kernels.run(timeout=0.01)
        self.assertEqual(get_many(q1), ['x'])
        self.assertEqual(get_many(q_out), [])
        self.assertTrue(multiplexer_task.is_completed())
        self.assertIsNone(multiplexer_task.get_result_nonblocking())

    @kernels.with_kernel
    def test_already_closed_output(self):
        q1 = queues.Queue()
        q_out = queues.Queue()
        q_out.close()
        multiplexer_task = tasks.spawn(more_queues.multiplex([q1], q_out))
        kernels.run(timeout=0.01)
        self.assertTrue(multiplexer_task.is_completed())
        self.assertIsNone(multiplexer_task.get_result_nonblocking())


def get_many(queue):
    result = []
    while True:
        try:
            result.append(queue.get_nonblocking())
        except (queues.Closed, queues.Empty):
            break
    return result


if __name__ == '__main__':
    unittest.main()
