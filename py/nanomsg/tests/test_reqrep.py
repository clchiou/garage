import unittest

import asyncio

import nanomsg as nn
from nanomsg.asyncio import Socket


class ReqrepTest(unittest.TestCase):

    def test_reqrep(self):

        result_1 = []
        result_2 = []

        async def ping(url):
            with Socket(protocol=nn.NN_REQ) as sock, sock.connect(url):
                await sock.send(b'ping')
                message = await sock.recv()
                result_1.append(bytes(message.as_memoryview()).decode('ascii'))

        async def pong(url):
            with Socket(protocol=nn.NN_REP) as sock, sock.bind(url):
                message = await sock.recv()
                result_2.append(bytes(message.as_memoryview()).decode('ascii'))
                await sock.send(b'pong')

        url = 'inproc://test'
        future = asyncio.wait(
            [
                asyncio.ensure_future(ping(url)),
                asyncio.ensure_future(pong(url)),
            ],
            return_when=asyncio.FIRST_EXCEPTION,
        )

        loop = asyncio.get_event_loop()
        done, _ = loop.run_until_complete(future)
        for fut in done:
            fut.result()

        self.assertEqual(['pong'], result_1)
        self.assertEqual(['ping'], result_2)


if __name__ == '__main__':
    unittest.main()
