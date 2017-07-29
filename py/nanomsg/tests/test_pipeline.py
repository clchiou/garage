import unittest

import asyncio

import nanomsg as nn
from nanomsg.asyncio import Socket


class PipelineTest(unittest.TestCase):

    def test_pipeline(self):

        result = []

        async def ping(url, ack):
            with Socket(protocol=nn.NN_PUSH) as sock, sock.connect(url):
                await sock.send(b'Hello, world!')
                await ack.wait()

        async def pong(url, ack):
            with Socket(protocol=nn.NN_PULL) as sock, sock.bind(url):
                message = await sock.recv()
                result.append(bytes(message.as_memoryview()).decode('ascii'))
                ack.set()

        url = 'inproc://test'
        ack = asyncio.Event()
        future = asyncio.wait(
            [
                asyncio.ensure_future(ping(url, ack)),
                asyncio.ensure_future(pong(url, ack)),
            ],
            return_when=asyncio.FIRST_EXCEPTION,
        )

        loop = asyncio.get_event_loop()
        done, _ = loop.run_until_complete(future)
        for fut in done:
            fut.result()

        self.assertEqual(['Hello, world!'], result)


if __name__ == '__main__':
    unittest.main()
