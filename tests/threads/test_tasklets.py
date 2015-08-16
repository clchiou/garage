import unittest

from garage.threads import actors
from garage.threads import queues
from garage.threads import tasklets
from garage.threads import utils


class TaskletsTest(unittest.TestCase):

    def test_tasklet(self):
        num_tasklets = 4
        expected_counter_value = 10

        task_queue = utils.TaskQueue(queues.Queue())
        tasklet_stubs = [
            tasklets.Tasklet.make(task_queue) for _ in range(num_tasklets)
        ]

        counter = utils.AtomicInt()
        for _ in range(expected_counter_value):
            task_queue.put(lambda: counter.get_and_add(1))

        task_queue.future.result()

        self.assertEqual(expected_counter_value, counter.get_and_set(0))
        for stub in tasklet_stubs:
            self.assertIsNone(stub.get_future().result())
            self.assertTrue(stub.get_future().done())


if __name__ == '__main__':
    unittest.main()
