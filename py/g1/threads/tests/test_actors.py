import unittest

import sys

from g1.threads import actors
from g1.threads import futures


class ActorsTest(unittest.TestCase):

    def test_object_based_actor(self):
        with actors.from_object(Base('Alice')) as stub:
            self.assertFalse(stub.queue.is_closed())
            self.assertFalse(stub.future.is_completed())

            expect = 'Hello, Bob! I am Alice.'
            self.assertEqual(stub.m.greet('Bob').get_result(), expect)

            self.assertFalse(stub.queue.is_closed())
            self.assertFalse(stub.future.is_completed())

        self.assertTrue(stub.queue.is_closed())
        self.assertEqual(len(stub.queue), 0)
        self.assertTrue(stub.future.is_completed())

    def test_object_based_actor_derived(self):
        with actors.from_object(Derived('Alice')) as stub:
            self.assertFalse(stub.queue.is_closed())
            self.assertFalse(stub.future.is_completed())

            expect = 'Hello, Bob! I am Alice, derived.'
            self.assertEqual(stub.m.greet('Bob').get_result(), expect)
            self.assertEqual(stub.m.inc(42).get_result(), 43)

            with self.assertRaises(TypeError):
                stub.m.inc('x').get_result()

            self.assertFalse(stub.queue.is_closed())
            self.assertFalse(stub.future.is_completed())

        self.assertTrue(stub.queue.is_closed())
        self.assertEqual(len(stub.queue), 0)
        self.assertTrue(stub.future.is_completed())

    def test_object_based_actor_invalid_message(self):
        with actors.from_object(Base('Alice')) as stub:
            stub.queue.put(None)
            with self.assertRaisesRegex(AssertionError, r'expect.*MethodCall'):
                stub.future.get_result()

    def test_object_based_actor_not_str(self):
        with actors.from_object(Base('Alice')) as stub:
            future = futures.Future()
            call = actors.MethodCall(
                method=None, args=(), kwargs={}, future=future
            )
            stub.queue.put(call)
            with self.assertRaisesRegex(AssertionError, r'expect.*str'):
                future.get_result()
            self.assertFalse(stub.future.is_completed())

    def test_function_caller(self):
        with actors.Stub(actor=actors.function_caller) as stub:
            self.assertFalse(stub.queue.is_closed())
            self.assertFalse(stub.future.is_completed())

            obj = Base('Alice')
            expect = 'Hello, Bob! I am Alice.'
            future = futures.Future()
            call = actors.MethodCall(
                method=obj.greet, args=('Bob', ), kwargs={}, future=future
            )
            stub.queue.put(call)
            self.assertEqual(future.get_result(), expect)

            future = futures.Future()
            call = actors.MethodCall(
                method=[].pop, args=(), kwargs={}, future=future
            )
            stub.queue.put(call)
            with self.assertRaises(IndexError):
                future.get_result()

            future = futures.Future()
            call = actors.MethodCall(
                method=sys.exit, args=(), kwargs={}, future=future
            )
            stub.queue.put(call)
            with self.assertRaises(SystemExit):
                future.get_result()

            self.assertFalse(stub.queue.is_closed())
            self.assertFalse(stub.future.is_completed())

        self.assertTrue(stub.queue.is_closed())
        self.assertEqual(len(stub.queue), 0)
        self.assertTrue(stub.future.is_completed())

    def test_function_caller_invalid_message(self):
        with actors.Stub(actor=actors.function_caller) as stub:
            stub.queue.put(None)
            with self.assertRaisesRegex(AssertionError, r'expect.*MethodCall'):
                stub.future.get_result()

    def test_function_caller_not_callable(self):
        with actors.Stub(actor=actors.function_caller) as stub:
            future = futures.Future()
            call = actors.MethodCall(
                method=None, args=(), kwargs={}, future=future
            )
            stub.queue.put(call)
            with self.assertRaisesRegex(AssertionError, r'expect.*callable'):
                future.get_result()
            self.assertFalse(stub.future.is_completed())


class Base:

    class SomeClass:
        pass

    @staticmethod
    def some_staticmethod_method():
        pass

    @classmethod
    def some_class_method(cls):
        pass

    @property
    def some_property(self):
        pass

    def __init__(self, name):
        self.name = name

    def greet(self, other):
        return 'Hello, %s! I am %s.' % (other, self.name)


class Derived(Base):

    def __init__(self, name, amount=1):
        super().__init__(name)
        self.amount = amount

    def inc(self, x):
        return x + self.amount

    def greet(self, other):
        return 'Hello, %s! I am %s, derived.' % (other, self.name)


if __name__ == '__main__':
    unittest.main()
