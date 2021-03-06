import unittest

import threading
import weakref

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

    @actors.method
    def side_effect(self, event):
        event.set()

    @actors.method
    def exit(self):
        raise actors.Exit


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


class GreeterWithInject(actors.Stub, actor=_Greeter):

    extra_args = ()
    extra_kwargs = {}

    def __init__(self, *args, **kwargs):
        args, kwargs = actors.inject(
            args, kwargs,
            GreeterWithInject.extra_args, GreeterWithInject.extra_kwargs,
        )
        super().__init__(*args, **kwargs)


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


class ActorsTest(unittest.TestCase):

    def test_actor_method_name(self):

        class _X:
            @actors.method
            def _x(self):
                pass

        with self.assertRaisesRegex(actors.ActorError, r'starts with "_"'):
            class X(actors.Stub, actor=_X):
                pass

    def test_actors(self):
        greeter = Greeter('John')
        self.assertEqual('Hello John', greeter.greet().result())
        self.assertEqual('Hello Paul', greeter.greet('Paul').result())
        self.assertFalse(greeter._get_future().done())

        greeter = Greeter()
        self.assertEqual('Hello world', greeter.greet().result())
        self.assertEqual('Hello Jean', greeter.greet('Jean').result())
        self.assertFalse(greeter._get_future().done())

        greeter = actors.build(Greeter, capacity=1, args=('Jean',))
        self.assertEqual('Hello Jean', greeter.greet().result())

        bomb = Bomb()
        future = bomb.explode()
        with self.assertRaisesRegex(Explosion, r'Boom!'):
            future.result()
        self.assertTrue(bomb._get_future().done())
        with self.assertRaisesRegex(
                actors.ActorError, r'actor has been killed'):
            bomb.explode()

        bomb = PoliteBomb('Bob')
        self.assertEqual('Hello Bob', bomb.greet().result())
        future = bomb.explode()
        with self.assertRaisesRegex(Explosion, r'Boom!'):
            future.result()
        self.assertTrue(bomb._get_future().done())

    def test_inject(self):
        GreeterWithInject.extra_args = ('John',)
        GreeterWithInject.extra_kwargs = {}
        greeter = GreeterWithInject()
        self.assertEqual('Hello John', greeter.greet().result())
        greeter = actors.build(GreeterWithInject)
        self.assertEqual('Hello John', greeter.greet().result())

        GreeterWithInject.extra_args = ()
        GreeterWithInject.extra_kwargs = {'name': 'John'}
        greeter = GreeterWithInject()
        self.assertEqual('Hello John', greeter.greet().result())
        greeter = actors.build(GreeterWithInject)
        self.assertEqual('Hello John', greeter.greet().result())

    def test_name(self):
        greeter = actors.build(Greeter, name='greeter-01')
        self.assertEqual('greeter-01', greeter._name)

    def test_weakref_1(self):
        blocker = Blocker()
        event = threading.Event()
        future_ref = weakref.ref(blocker.side_effect(event))
        self.assertIsNone(future_ref())
        self.assertTrue(event.wait(timeout=0.1))

    def test_weakref_2(self):
        future_ref = weakref.ref(Greeter()._get_future())
        self.assertIsNone(future_ref())

    def test_finalize(self):
        greeter = Greeter()
        future = greeter._get_future()
        del greeter
        self.assertIsNone(future.result(timeout=0.1))

    def test_busy(self):
        blocker = Blocker()

        barrier = threading.Barrier(2)
        event = threading.Event()
        future = blocker.wait(barrier, event)

        barrier.wait()

        event.set()
        future.result()

    def test_return(self):

        actual = []

        class _Foo:

            @actors.method
            def func1(self):
                actual.append(1)
                raise actors.Return(None, _Foo.func2)

            @actors.method
            def func2(self):
                actual.append(2)
                raise actors.Exit

        class Foo(actors.Stub, actor=_Foo):
            pass

        foo = Foo()
        foo.func1().result()
        foo._get_future().result()
        self.assertEqual([1, 2], actual)

    def test_exit(self):
        blocker = Blocker()
        event = threading.Event()
        blocker.wait(None, event)

        # Enque in order.
        exit_fut = blocker.exit()
        side_effect_fut = blocker.side_effect(threading.Event())

        # Unblock it.
        event.set()

        self.assertFalse(blocker._get_future().done())
        with self.assertRaises(actors.Exit):
            exit_fut.result()
        self.assertTrue(blocker._get_future().done())
        self.assertTrue(side_effect_fut.cancelled())

    def test_kill(self):
        for graceful in (True, False):
            greeter = Greeter()
            self.assertFalse(greeter._get_future().done())
            self.assertEqual('Hello world', greeter.greet().result())

            greeter._kill(graceful=graceful)

            with self.assertRaisesRegex(
                    actors.ActorError, r'actor has been killed'):
                greeter.greet()

            greeter._get_future().result(timeout=1)
            self.assertTrue(greeter._get_future().done())

        blocker = Blocker()
        barrier = threading.Barrier(2)
        event = threading.Event()
        blocker.wait(barrier, event)
        barrier.wait()
        blocker._kill(graceful=False)
        self.assertFalse(blocker._get_future().done())
        self.assertFalse(blocker._Stub__msg_queue)

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


class OneShotActorTest(unittest.TestCase):

    def test_one_off_actor(self):
        summer = actors.OneShotActor(sum)
        self.assertEqual(6, summer([1, 2, 3])._get_future().result())

        summer = actors.OneShotActor(sum)
        stub = summer(actors.BUILD, name='summer', args=([7, 8], ))
        self.assertEqual(15, stub._get_future().result())


class StubPoolTest(unittest.TestCase):

    def test_stub_pool(self):

        pool = actors.StubPool([Greeter('John'), Greeter('Paul')])
        self.assertEqual(
            ['Hello John', 'Hello Paul'],
            [pool.greet().result(), pool.greet().result()],
        )

        pool._kill()
        pool._get_future().result()

        with self.assertRaisesRegex(RuntimeError, 'no stub available'):
            pool.greet()


if __name__ == '__main__':
    unittest.main()
