import unittest

import asyncio

from nanomsg.asyncio import Socket
import nanomsg as nn

from tests.utils import Barrier


class PubSubTest(unittest.TestCase):

    def test_pubsub(self):

        result = []

        async def sender(url, topic, barrier):
            with Socket(protocol=nn.NN_PUB) as sock, sock.bind(url):
                await sock.send(b'%s|ping' % topic)
                await sock.send(b'NOT-ON-%s|ping' % topic)
                await barrier.wait()

        async def receiver(url, topic, barrier):
            with Socket(protocol=nn.NN_SUB) as sock:
                sock.options.nn_sub_subscribe = topic
                with sock.connect(url):
                    message = await sock.recv()
                    result.append(
                        bytes(message.as_memoryview()).decode('ascii'))
                await barrier.wait()

        url = 'inproc://test'
        topic = b'TOPIC'
        barrier = Barrier(2)
        future = asyncio.wait(
            [
                asyncio.ensure_future(sender(url, topic, barrier)),
                asyncio.ensure_future(receiver(url, topic, barrier)),
            ],
            return_when=asyncio.FIRST_EXCEPTION,
        )

        loop = asyncio.get_event_loop()
        done, _ = loop.run_until_complete(future)
        for fut in done:
            fut.result()

        self.assertEqual(['TOPIC|ping'], result)


if __name__ == '__main__':
    unittest.main()
