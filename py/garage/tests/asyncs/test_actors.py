import unittest

from tests.availability import curio_available

if curio_available:
    import curio
    from garage.threads import actors
    from garage.asyncs.actors import StubAdapter
    from garage.asyncs.utils import synchronous
else:
    def synchronous(func):
        return func


@unittest.skipUnless(curio_available, 'curio unavailable')
class ActorsTest(unittest.TestCase):

    @synchronous
    async def test_actor(self):

        class _Actor:

            @actors.method
            def hello(self):
                return 'hello'

        class Actor(actors.Stub, actor=_Actor):
            pass

        stub = StubAdapter(actors.build(Actor, name='test-actor'))

        async with curio.timeout_after(0.01):
            self.assertEqual('hello', await stub.hello().result())

        # Test adapter's simple foolproof detection
        self.assertEqual('test-actor', stub._name)

        stub._kill()
        async with curio.timeout_after(0.01):
            await stub._get_future().result()


if __name__ == '__main__':
    unittest.main()
