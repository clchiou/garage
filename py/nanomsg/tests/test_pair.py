import unittest

import asyncio

from nanomsg.asyncio import Socket
import nanomsg as nn

from tests.utils import Barrier


class PairTest(unittest.TestCase):

    def test_pair(self):

        result_1 = []
        result_2 = []

        async def ping(url, barrier):
            with Socket(protocol=nn.NN_PAIR) as sock, sock.connect(url):
                await sock.send(b'ping')
                message = await sock.recv()
                result_1.append(
                    bytes(message.as_memoryview()).decode('ascii'))
                await barrier.wait()

        async def pong(url, barrier):
            with Socket(protocol=nn.NN_PAIR) as sock, sock.bind(url):
                await sock.send(b'pong')
                message = await sock.recv()
                result_2.append(
                    bytes(message.as_memoryview()).decode('ascii'))
                await barrier.wait()

        url = 'inproc://test'
        barrier = Barrier(2)
        future = asyncio.wait(
            [
                asyncio.ensure_future(ping(url, barrier)),
                asyncio.ensure_future(pong(url, barrier)),
            ],
            return_when=asyncio.FIRST_EXCEPTION,
        )
        loop = asyncio.get_event_loop()
        for fut in loop.run_until_complete(future)[0]:
            fut.result()

        self.assertEqual(['pong'], result_1)
        self.assertEqual(['ping'], result_2)


if __name__ == '__main__':
    unittest.main()
