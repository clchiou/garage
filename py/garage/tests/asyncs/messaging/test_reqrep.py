import unittest

import random

import curio

from nanomsg.curio import Socket
import nanomsg as nn

from garage.asyncs import TaskStack
from garage.asyncs.futures import Future, State
from garage.asyncs.messaging import reqrep
from garage.asyncs.queues import Queue, ZeroQueue
from garage.asyncs.utils import synchronous


URL_BASE = 'inproc://test_reqrep/'


class ReqrepTest(unittest.TestCase):

    def setUp(self):
        self.url = URL_BASE + str(random.randint(0, 65536))

    @synchronous
    async def test_cancel_client(self):
        async with Socket(protocol=nn.NN_REQ) as socket, TaskStack() as stack:
            socket.connect(self.url)
            queue = Queue()
            client_task = await stack.spawn(reqrep.client(socket, queue))

            response_future = Future()
            await queue.put((b'', response_future.make_promise()))

            await client_task.cancel()

            self.assertTrue(response_future.state is State.PENDING)
            self.assertEqual('CANCELLED', client_task.state)

    @synchronous
    async def test_cancel_server(self):
        async with Socket(protocol=nn.NN_REP) as socket, TaskStack() as stack:
            socket.bind(self.url)
            queue = ZeroQueue()
            server_task = await stack.spawn(reqrep.server(socket, queue))

            await server_task.cancel()

            self.assertEqual('CANCELLED', server_task.state)

    @synchronous
    async def test_end_to_end(self):
        async with Socket(protocol=nn.NN_REQ) as client_socket, \
                   Socket(protocol=nn.NN_REP) as server_socket, \
                   TaskStack() as stack:

            client_socket.connect(self.url)
            client_queue = Queue()
            client_task = await stack.spawn(
                reqrep.client(client_socket, client_queue))

            server_socket.bind(self.url)
            server_queue = Queue()
            server_task = await stack.spawn(
                reqrep.server(server_socket, server_queue))

            client_request = b'hello'
            client_response_future = Future()
            await client_queue.put(
                (client_request, client_response_future.make_promise()))

            server_request, server_response_promise = await server_queue.get()
            self.assertEqual(client_request, server_request)

            expect = b'world'
            await server_response_promise.set_result(expect)
            self.assertEqual(expect, await client_response_future.get_result())

    @synchronous
    async def test_client_timeout(self):
        async with Socket(protocol=nn.NN_REQ) as socket, TaskStack() as stack:
            socket.connect(self.url)
            queue = Queue()
            client_task = await stack.spawn(
                reqrep.client(socket, queue, timeout=0.01))

            response_future = Future()
            await queue.put((b'', response_future.make_promise()))

            try:
                await response_future.get_result()
                self.fail('get_result() did not raise')
            except curio.TaskTimeout:
                pass

    @synchronous
    async def test_server_timeout(self):
        async with Socket(protocol=nn.NN_REP) as socket, TaskStack() as stack:
            socket.bind(self.url)
            queue = Queue()
            server_task = await stack.spawn(
                reqrep.server(socket, queue, timeout=0.01))

            async with Socket(protocol=nn.NN_REQ) as client_socket:
                client_socket.connect(self.url)
                await client_socket.send(b'')

                try:
                    await server_task.join()
                    self.fail('join() did not raise')
                except curio.TaskError as exc:
                    self.assertTrue(
                        isinstance(exc.__cause__, curio.TaskTimeout))


if __name__ == '__main__':
    unittest.main()
