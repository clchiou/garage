import unittest

import asyncio
import random

from garage.asyncs import queues
from garage.asyncs.messaging import reqrep

from .. import synchronous


URL_BASE = 'inproc://test_reqrep/'


class ReqrepTest(unittest.TestCase):

    def setUp(self):
        self.url = URL_BASE + str(random.randint(0, 65536))

    @synchronous
    async def test_stop_client(self):
        client = reqrep.client(self.url)

        response_fut = asyncio.Future()
        await client.inbox.put((b'', response_fut))

        client.stop()
        await client

        self.assertTrue(client.task.done())
        self.assertFalse(response_fut.cancelled())

        response_fut.cancel()

    @synchronous
    async def test_stop_server(self):
        client = reqrep.client(self.url)
        client_response_fut = asyncio.Future()
        await client.inbox.put((b'hello world', client_response_fut))

        server = reqrep.server(self.url)

        request, response_fut = await server.inbox.get()
        self.assertEqual(b'hello world', request)
        self.assertIsNot(client_response_fut, response_fut)

        server.stop()
        await server

        self.assertTrue(server.task.done())
        self.assertTrue(response_fut.cancelled())

        client.stop()
        await client
        self.assertFalse(client_response_fut.cancelled())
        self.assertIsNotNone(client_response_fut.exception())
        self.assertTrue(
            isinstance(client_response_fut.exception(), queues.Closed))

        client_response_fut.cancel()

    @synchronous
    async def test_end_to_end(self):
        client = reqrep.client(self.url)
        server = reqrep.server(self.url)

        client_request = b'hello'
        client_response_fut = asyncio.Future()
        await client.inbox.put((client_request, client_response_fut))

        server_request, server_response_fut = await server.inbox.get()
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
        client = reqrep.client(self.url, timeout=0.01)

        response_fut = asyncio.Future()
        await client.inbox.put((b'', response_fut))

        with self.assertRaises(asyncio.TimeoutError):
            await response_fut

        client.stop()
        await client

    @synchronous
    async def test_server_timeout(self):
        client = reqrep.client(self.url)
        client_response_fut = asyncio.Future()
        await client.inbox.put((b'hello world', client_response_fut))

        server = reqrep.server(
            self.url,
            timeout=0.01,
            timeout_response=b'timeout',
        )

        request, response_fut = await server.inbox.get()
        self.assertEqual(b'hello world', request)

        self.assertEqual(b'timeout', await client_response_fut)
        self.assertTrue(response_fut.cancelled())

        client.stop()
        await client

        server.stop()
        await server

    @synchronous
    async def test_server_timeout_crash(self):
        client = reqrep.client(self.url)
        client_response_fut = asyncio.Future()
        await client.inbox.put((b'hello world', client_response_fut))

        server = reqrep.server(
            self.url,
            timeout=0.01,
        )

        request, response_fut = await server.inbox.get()
        self.assertEqual(b'hello world', request)

        with self.assertRaises(asyncio.TimeoutError):
            await server
        self.assertTrue(response_fut.cancelled())

        client_response_fut.cancel()

        client.stop()
        await client


if __name__ == '__main__':
    unittest.main()
