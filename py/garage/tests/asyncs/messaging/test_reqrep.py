import unittest

from tests.availability import curio_available, nanomsg_available

import random

if curio_available and nanomsg_available:
    import curio
    from nanomsg.curio import Socket
    import nanomsg as nn
    from garage import asyncs
    from garage.asyncs.futures import Future
    from garage.asyncs.messaging import reqrep
    from garage.asyncs.queues import Queue, ZeroQueue
    from garage.asyncs.utils import synchronous


URL_BASE = 'inproc://test_reqrep/'


@unittest.skipUnless(
    curio_available and nanomsg_available, 'curio or nanomsg unavailable')
class ReqrepTest(unittest.TestCase):

    def setUp(self):
        self.url = URL_BASE + str(random.randint(0, 65536))

    @synchronous
    async def test_cancel_client(self):
        socket = Socket(protocol=nn.NN_REQ)
        async with socket, asyncs.TaskStack() as stack:
            socket.connect(self.url)
            queue = Queue()
            client_task = await stack.spawn(reqrep.client(socket, queue))

            response_future = Future()
            await queue.put((b'', response_future.promise()))

            await client_task.cancel()

            self.assertTrue(response_future.running())
            self.assertTrue(client_task.cancelled)

    @synchronous
    async def test_cancel_server(self):
        socket = Socket(domain=nn.AF_SP_RAW, protocol=nn.NN_REP)
        async with socket, asyncs.TaskStack() as stack:
            socket.bind(self.url)
            queue = ZeroQueue()
            server_task = await stack.spawn(
                reqrep.server(asyncs.Event(), socket, queue))
            await server_task.cancel()
            self.assertTrue(server_task.cancelled)

    @synchronous
    async def test_end_to_end(self):
        client_socket = Socket(protocol=nn.NN_REQ)
        server_socket = Socket(domain=nn.AF_SP_RAW, protocol=nn.NN_REP)
        async with client_socket, server_socket, asyncs.TaskStack() as stack:

            client_socket.connect(self.url)
            client_queue = Queue()
            client_task = await stack.spawn(
                reqrep.client(client_socket, client_queue))

            server_socket.bind(self.url)
            server_queue = Queue()
            server_task = await stack.spawn(
                reqrep.server(asyncs.Event(), server_socket, server_queue))

            client_request = b'hello'
            client_response_future = Future()
            await client_queue.put(
                (client_request, client_response_future.promise()))

            server_request, server_response_promise = await server_queue.get()
            self.assertEqual(client_request, server_request)

            expect = b'world'
            server_response_promise.set_result(expect)
            self.assertEqual(expect, await client_response_future.result())

    @synchronous
    async def test_client_timeout(self):
        socket = Socket(protocol=nn.NN_REQ)
        async with socket, asyncs.TaskStack() as stack:
            socket.connect(self.url)
            queue = Queue()
            client_task = await stack.spawn(
                reqrep.client(socket, queue, timeout=0.01))

            response_future = Future()
            await queue.put((b'', response_future.promise()))

            with self.assertRaises(reqrep.Unavailable):
                await response_future.result()

    @synchronous
    async def test_server_timeout(self):
        socket = Socket(domain=nn.AF_SP_RAW, protocol=nn.NN_REP)
        async with socket, asyncs.TaskStack() as stack:

            def error_handler(_, exc):
                if isinstance(exc, reqrep.Unavailable):
                    return b'unavailable'
                else:
                    return None

            graceful_exit = asyncs.Event()

            socket.bind(self.url)

            server_task = await stack.spawn(reqrep.server(
                graceful_exit, socket, Queue(),
                timeout=0.01,
                error_handler=error_handler,
            ))

            async with Socket(protocol=nn.NN_REQ) as client_socket:
                client_socket.connect(self.url)
                await client_socket.send(b'')
                msg = await client_socket.recv()
                self.assertEqual(b'unavailable', bytes(msg.as_memoryview()))

            graceful_exit.set()
            await server_task.join()


if __name__ == '__main__':
    unittest.main()
