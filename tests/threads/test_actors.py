import unittest

import threading

from garage.threads import actors


class _Greeter:

    def __init__(self, name='world'):
        self.name = name

    @actors.method
    def greet(self, name=None):
        return 'Hello %s' % (name or self.name)


class Explosion(Exception):
    pass


class _Bomb:

    @actors.method
    def explode(self):
        raise Explosion('Boom!')


class _PoliteBomb(_Greeter, _Bomb):
    pass


class _Blocker:

    @actors.method
    def wait(self, barrier, event):
        if barrier:
            barrier.wait()
        event.wait()


class _A:

    @actors.method
    def do_something(self):
        return 'A'


class _B:

    @actors.method
    def do_something(self):
        return 'B'


class _C(_A, _B):
    pass


class _D(_B, _A):
    pass


class Greeter(actors.Stub, actor=_Greeter):
    pass


class Bomb(actors.Stub, actor=_Bomb):
    pass


class PoliteBomb(actors.Stub, actor=_PoliteBomb):
    pass


class Blocker(actors.Stub, actor=_Blocker):
    pass


class C(actors.Stub, actor=_C):
    pass


class D(actors.Stub, actor=_D):
    pass


class TestActors(unittest.TestCase):

    def test_actors(self):
        greeter = Greeter('John')
        self.assertEqual('Hello John', greeter.greet().result())
        self.assertEqual('Hello Paul', greeter.greet('Paul').result())
        self.assertFalse(greeter.get_future().done())

        greeter = Greeter()
        self.assertEqual('Hello world', greeter.greet().result())
        self.assertEqual('Hello Jean', greeter.greet('Jean').result())
        self.assertFalse(greeter.get_future().done())

        greeter = actors.build(Greeter, capacity=1, args=('Jean',))
        self.assertEqual('Hello Jean', greeter.greet().result())

        bomb = Bomb()
        future = bomb.explode()
        with self.assertRaisesRegex(Explosion, r'Boom!'):
            future.result()
        self.assertTrue(bomb.get_future().done())
        with self.assertRaisesRegex(actors.ActorError, r'actor is dead'):
            bomb.explode()

        bomb = PoliteBomb('Bob')
        self.assertEqual('Hello Bob', bomb.greet().result())
        future = bomb.explode()
        with self.assertRaisesRegex(Explosion, r'Boom!'):
            future.result()
        self.assertTrue(bomb.get_future().done())

    def test_busy(self):
        blocker = Blocker()

        barrier = threading.Barrier(2)
        event = threading.Event()
        future = blocker.wait(barrier, event)

        barrier.wait()

        event.set()
        future.result()

    def test_kill(self):
        for graceful in (True, False):
            greeter = Greeter()
            self.assertFalse(greeter.get_future().done())
            self.assertEqual('Hello world', greeter.greet().result())

            greeter.kill(graceful=graceful)

            with self.assertRaisesRegex(
                    actors.ActorError, r'actor is being killed'):
                greeter.greet()

            greeter.get_future().result(timeout=1)
            self.assertTrue(greeter.get_future().done())

        blocker = Blocker()
        event = threading.Event()
        blocker.wait(None, event)
        blocker.wait(None, event)
        blocker.kill(graceful=False)
        self.assertFalse(blocker.get_future().done())
        self.assertFalse(blocker._Stub__work_queue)

    def test_mro(self):
        self.assertEqual('A', C().do_something().result())
        self.assertEqual('B', D().do_something().result())

    def test_invalid_actors(self):
        with self.assertRaisesRegex(actors.ActorError, r'is not a stub'):
            actors.Stub()

        with self.assertRaisesRegex(actors.ActorError, r'not a function'):
            @actors.method
            @staticmethod
            def foo():
                pass

        with self.assertRaisesRegex(actors.ActorError, r'not a function'):
            @actors.method
            @classmethod
            def foo():
                pass

        with self.assertRaisesRegex(actors.ActorError, r'should not override'):
            class Foo(actors.Stub, actor=_Greeter):
                def greet(self):
                    pass


if __name__ == '__main__':
    unittest.main()
