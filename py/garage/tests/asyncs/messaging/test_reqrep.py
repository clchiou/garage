import unittest

import asyncio
import random

from garage.asyncs import queues
from garage.asyncs.futures import each_completed
from garage.asyncs.messaging import reqrep
from garage.asyncs.utils import synchronous


URL_BASE = 'inproc://test_reqrep/'


class ReqrepTest(unittest.TestCase):

    def setUp(self):
        self.url = URL_BASE + str(random.randint(0, 65536))

    @synchronous
    async def test_stop_client(self):
        rq = queues.Queue()
        client = asyncio.ensure_future(reqrep.client(self.url, rq))

        response_fut = asyncio.Future()
        await rq.put((b'', response_fut))

        client.stop()
        await client

        self.assertTrue(client.done())
        self.assertFalse(response_fut.cancelled())

        response_fut.cancel()

    @synchronous
    async def test_stop_server(self):

        flag = asyncio.Event()

        async def run_client():
            client_rq = queues.Queue()
            client = asyncio.ensure_future(reqrep.client(self.url, client_rq))
            client_response_fut = asyncio.Future()
            await client_rq.put((b'hello world', client_response_fut))

            await flag.wait()

            client.stop()
            await client

            self.assertFalse(client_response_fut.done())
            self.assertFalse(client_response_fut.cancelled())
            client_response_fut.cancel()

        async def run_server():
            server_rq = queues.Queue()
            server = asyncio.ensure_future(reqrep.server(self.url, server_rq))

            request, response_fut = await server_rq.get()
            self.assertEqual(b'hello world', request)

            flag.set()

            server.stop()
            await server
            self.assertTrue(response_fut.cancelled())

        async for task in each_completed([run_client(), run_server()]):
            await task

    @synchronous
    async def test_end_to_end(self):
        client_rq = queues.Queue()
        client = reqrep.client(self.url, client_rq)
        server_rq = queues.Queue()
        server = reqrep.server(self.url, server_rq)

        client_request = b'hello'
        client_response_fut = asyncio.Future()
        await client_rq.put((client_request, client_response_fut))

        server_request, server_response_fut = await server_rq.get()
        self.assertEqual(client_request, server_request)

        expect = b'world'
        server_response_fut.set_result(expect)
        self.assertEqual(expect, await client_response_fut)

        client.stop()
        await client

        server.stop()
        await server

    @synchronous
    async def test_client_timeout(self):
        client_rq = queues.Queue()
        client = reqrep.client(self.url, client_rq, timeout=0.01)

        response_fut = asyncio.Future()
        await client_rq.put((b'', response_fut))

        with self.assertRaises(asyncio.TimeoutError):
            await response_fut

        client.stop()
        await client

    @synchronous
    async def test_server_timeout(self):
        client_rq = queues.Queue()
        client = reqrep.client(self.url, client_rq)
        client_response_fut = asyncio.Future()
        await client_rq.put((b'hello world', client_response_fut))

        server_rq = queues.Queue()
        server = reqrep.server(
            self.url,
            server_rq,
            timeout=0.01,
            timeout_response=b'timeout',
        )

        request, response_fut = await server_rq.get()
        self.assertEqual(b'hello world', request)

        self.assertEqual(b'timeout', await client_response_fut)
        self.assertTrue(response_fut.cancelled())

        client.stop()
        await client

        server.stop()
        await server

    @synchronous
    async def test_server_timeout_crash(self):
        client_rq = queues.Queue()
        client = reqrep.client(self.url, client_rq)
        client_response_fut = asyncio.Future()
        await client_rq.put((b'hello world', client_response_fut))

        server_rq = queues.Queue()
        server = reqrep.server(
            self.url,
            server_rq,
            timeout=0.01,
        )

        request, response_fut = await server_rq.get()
        self.assertEqual(b'hello world', request)

        with self.assertRaises(asyncio.TimeoutError):
            await server
        self.assertTrue(response_fut.cancelled())

        client_response_fut.cancel()

        client.stop()
        await client


if __name__ == '__main__':
    unittest.main()
