import unittest

import contextlib
import dataclasses

from g1.asyncs import kernels
from g1.asyncs.bases import queues
from g1.asyncs.bases import tasks
from g1.messaging.pubsub import publishers
from g1.messaging.pubsub import subscribers
from g1.messaging.wiredata import jsons


@dataclasses.dataclass(frozen=True)
class Message:
    content: str


class PubsubTest(unittest.TestCase):

    @kernels.with_kernel
    def test_pubsub(self):
        with contextlib.ExitStack() as stack:
            wiredata = jsons.JsonWireData()
            p_queue = queues.Queue()
            s1_queue = queues.Queue()
            s2_queue = queues.Queue()
            publisher = stack.enter_context(
                publishers.Publisher(p_queue, wiredata)
            )
            subscriber1 = stack.enter_context(
                subscribers.Subscriber(Message, s1_queue, wiredata)
            )
            subscriber2 = stack.enter_context(
                subscribers.Subscriber(Message, s2_queue, wiredata)
            )
            publisher.socket.listen('inproc://test_pubsub')
            subscriber1.socket.dial('inproc://test_pubsub')
            subscriber2.socket.dial('inproc://test_pubsub')
            p_task = tasks.spawn(publisher.serve())
            s1_task = tasks.spawn(subscriber1.serve())
            s2_task = tasks.spawn(subscriber2.serve())
            with self.assertRaises(kernels.KernelTimeout):
                # Unfortunately this test is a somehow timing sensitive.
                # If we remove this kernels.run call, the subscribers
                # might sometimes not receive all messages.
                kernels.run(timeout=0.01)
            expect = (Message(content='hello'), Message(content='world'))
            for message in expect:
                publisher.publish_nonblocking(message)
            self.assertFalse(s1_queue)
            self.assertFalse(s2_queue)
            with self.assertRaises(kernels.KernelTimeout):
                kernels.run(timeout=0.01)
            self.assertEqual(len(s1_queue), 2)
            self.assertEqual(len(s2_queue), 2)
            for message in expect:
                self.assertEqual(s1_queue.get_nonblocking(), message)
                self.assertEqual(s2_queue.get_nonblocking(), message)

            publisher.shutdown()
            subscriber1.shutdown()
            subscriber2.shutdown()
            kernels.run(timeout=0.01)
            self.assertIsNone(p_task.get_result_nonblocking())
            self.assertIsNone(s1_task.get_result_nonblocking())
            self.assertIsNone(s2_task.get_result_nonblocking())


if __name__ == '__main__':
    unittest.main()
