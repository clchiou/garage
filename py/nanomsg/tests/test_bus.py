import unittest

import asyncio

from nanomsg.asyncio import Socket
import nanomsg as nn

from tests.utils import Barrier


class BusTest(unittest.TestCase):

    def test_bus(self):

        result = []

        async def sender(url, barrier):
            with Socket(protocol=nn.NN_BUS) as sock, sock.bind(url):
                await sock.send(b'ping')
                await barrier.wait()

        async def receiver(url, barrier):
            with Socket(protocol=nn.NN_BUS) as sock, sock.connect(url):
                message = await sock.recv()
                result.append(bytes(message.as_memoryview()).decode('ascii'))
                await barrier.wait()

        num_receivers = 3
        url = 'inproc://test'
        barrier = Barrier(1 + num_receivers)
        future = asyncio.wait(
            [
                asyncio.ensure_future(sender(url, barrier)),
            ] + [
                asyncio.ensure_future(receiver(url, barrier))
                for _ in range(num_receivers)
            ],
            return_when=asyncio.FIRST_EXCEPTION,
        )
        loop = asyncio.get_event_loop()
        for fut in loop.run_until_complete(future)[0]:
            fut.result()

        self.assertEqual(['ping'] * num_receivers, result)


if __name__ == '__main__':
    unittest.main()
