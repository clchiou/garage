import unittest

from garage.threads import actors
from garage.threads import queues
from garage.threads import tasklets
from garage.threads import utils


class TaskletsTest(unittest.TestCase):

    def test_task_queue(self):
        task_queue = tasklets.TaskQueue(queues.Queue())
        self.assertFalse(task_queue.is_closed())

        task_queue.put(1)
        self.assertFalse(task_queue.is_closed())

        task_queue.put(2)
        self.assertFalse(task_queue.is_closed())

        self.assertEqual(1, task_queue.get_task())
        self.assertFalse(task_queue.is_closed())

        task_queue.notify_tasklet_idle()
        self.assertFalse(task_queue.is_closed())

        self.assertEqual(2, task_queue.get_task())
        self.assertFalse(task_queue.is_closed())

        # This will trigger auto-close.
        task_queue.notify_tasklet_idle()
        self.assertTrue(task_queue.is_closed())

    def test_tasklet(self):
        num_tasklets = 4
        expected_counter_value = 10

        task_queue = tasklets.TaskQueue(queues.Queue())
        tasklet_stubs = [
            tasklets.tasklet(task_queue) for _ in range(num_tasklets)
        ]

        counter = utils.AtomicInt()
        for _ in range(expected_counter_value):
            task_queue.put(lambda: counter.get_and_add(1))

        for stub in tasklet_stubs:
            self.assertIsNone(stub._get_future().result())
            self.assertTrue(stub._get_future().done())

        self.assertEqual(expected_counter_value, counter.get_and_set(0))


if __name__ == '__main__':
    unittest.main()
