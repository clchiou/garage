import unittest

import curio

import nanomsg as nn
from nanomsg.curio import Socket


class CurioPipelineTest(unittest.TestCase):

    def test_pipeline(self):

        ack = curio.Event()
        result = []

        async def ping(url, ack):
            async with Socket(protocol=nn.NN_PUSH) as sock, sock.connect(url):
                await sock.send(b'Hello, world!')
                await ack.wait()

        async def pong(url, ack):
            async with Socket(protocol=nn.NN_PULL) as sock, sock.bind(url):
                message = await sock.recv()
                result.append(bytes(message.as_memoryview()).decode('ascii'))
                await ack.set()

        async def run():
            url = 'inproc://test'
            ping_task = await curio.spawn(ping(url, ack))
            pong_task = await curio.spawn(pong(url, ack))
            await ping_task.join()
            await pong_task.join()

        curio.run(run())

        self.assertEqual(['Hello, world!'], result)


if __name__ == '__main__':
    unittest.main()
