import unittest

import curio

from garage.threads import actors
from garage.asyncs.actors import AsyncStub

from tests.asyncs.utils import synchronous


class _Actor:

    @actors.method
    def hello(self):
        return 'hello'


class Actor(AsyncStub, actor=_Actor):
    pass


class ActorsTest(unittest.TestCase):

    @synchronous
    async def test_actor(self):
        stub = Actor()

        async with curio.timeout_after(0.01):
            self.assertEqual('hello', await stub.hello().result())

        stub.kill()
        async with curio.timeout_after(0.01):
            await stub.get_future().result()


if __name__ == '__main__':
    unittest.main()
