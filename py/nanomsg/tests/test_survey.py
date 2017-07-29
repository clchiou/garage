import unittest

import asyncio

from nanomsg.asyncio import Socket
import nanomsg as nn

from tests.utils import Barrier


class SurveyTest(unittest.TestCase):

    def test_survey(self):

        url = 'inproc://test'
        num_respondents = 2
        barrier_1 = Barrier(1 + num_respondents)
        barrier_2 = Barrier(1 + num_respondents)

        result_1 = []
        result_2 = []

        async def ping():
            with Socket(protocol=nn.NN_SURVEYOR) as sock, sock.bind(url):
                sock.options.nn_surveyor_deadline = 50  # Unit: ms.
                await barrier_1.wait()
                await sock.send(b'ping')
                for _ in range(num_respondents):
                    message = await sock.recv()
                    result_1.append(
                        bytes(message.as_memoryview()).decode('ascii'))
                await barrier_2.wait()
                try:
                    await sock.recv()
                except nn.ETIMEDOUT:
                    pass

        async def pong():
            with Socket(protocol=nn.NN_RESPONDENT) as sock, sock.connect(url):
                await barrier_1.wait()
                message = await sock.recv()
                result_2.append(
                    bytes(message.as_memoryview()).decode('ascii'))
                await sock.send(b'pong')
                await barrier_2.wait()

        future = asyncio.wait(
            [
                asyncio.ensure_future(ping()),
            ] + [
                asyncio.ensure_future(pong())
                for _ in range(num_respondents)
            ],
            return_when=asyncio.FIRST_EXCEPTION,
        )

        loop = asyncio.get_event_loop()
        for fut in loop.run_until_complete(future)[0]:
            fut.result()

        self.assertEqual(['pong'] * num_respondents, result_1)
        self.assertEqual(['ping'] * num_respondents, result_2)


if __name__ == '__main__':
    unittest.main()
