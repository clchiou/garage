import unittest

from garage import actors


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


class Greeter(actors.Stub, actor=_Greeter):
    pass


class Bomb(actors.Stub, actor=_Bomb):
    pass


class PoliteBomb(actors.Stub, actor=_PoliteBomb):
    pass


class TestActors(unittest.TestCase):

    def test_actors(self):
        with self.assertRaisesRegex(actors.ActorError, r'is not a stub'):
            actors.Stub()

        greeter = Greeter('John')
        self.assertEqual('Hello John', greeter.greet().result())
        self.assertEqual('Hello Paul', greeter.greet('Paul').result())
        self.assertFalse(greeter.is_dead())

        greeter = Greeter()
        self.assertEqual('Hello world', greeter.greet().result())
        self.assertEqual('Hello Jean', greeter.greet('Jean').result())
        self.assertFalse(greeter.is_dead())

        greeter = actors.build(Greeter, maxsize=1, args=('Jean',))
        self.assertEqual('Hello Jean', greeter.greet().result())

        bomb = Bomb()
        future = bomb.explode()
        with self.assertRaisesRegex(Explosion, r'Boom!'):
            future.result()
        self.assertTrue(bomb.is_dead())
        with self.assertRaisesRegex(actors.ActorError, r'actor is dead'):
            bomb.explode()

        bomb = PoliteBomb('Bob')
        self.assertEqual('Hello Bob', bomb.greet().result())
        future = bomb.explode()
        with self.assertRaisesRegex(Explosion, r'Boom!'):
            future.result()
        self.assertTrue(bomb.is_dead())

    def test_invalid_actors(self):
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
