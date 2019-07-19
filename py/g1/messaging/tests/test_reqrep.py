import unittest

import dataclasses
import typing

from g1.messaging import reqrep


@dataclasses.dataclass
class TestData:
    name: str


class TestInterface:

    @staticmethod
    def some_static_method():
        pass

    @classmethod
    def some_class_method(cls):
        pass

    @property
    def some_property(self):
        pass

    def _private_method(self):
        pass

    def square(self, x: int) -> int:
        raise NotImplementedError

    @reqrep.raising(Exception)
    def greet(self, name: TestData):
        raise NotImplementedError

    def test_default(self, s: str = 'hello world'):
        raise NotImplementedError


class ReqrepTest(unittest.TestCase):

    def test_raising(self):

        with self.assertRaises(AssertionError):
            reqrep.raising(int)

        @reqrep.raising()
        @reqrep.raising(ValueError, RuntimeError)
        @reqrep.raising()
        @reqrep.raising(IndexError)
        @reqrep.raising()
        def f():
            pass

        self.assertEqual(
            reqrep.get_interface_metadata(f).raising,
            (IndexError, ValueError, RuntimeError),
        )

    def test_method_signature(self):

        @reqrep.raising(Exception)
        def f(x: int, y: int = 1):
            return x + y

        def g() -> str:
            pass

        self.assertEqual(
            reqrep.MethodSignature.from_method(f),
            reqrep.MethodSignature(
                parameters=[('x', int), ('y', int)],
                defaults={'y': 1},
                return_type=None,
                raising=(Exception, ),
            ),
        )

        self.assertEqual(
            reqrep.MethodSignature.from_method(g),
            reqrep.MethodSignature(
                parameters=[],
                defaults={},
                return_type=str,
                raising=(),
            ),
        )

    def assert_fields(self, actual, expect):
        self.assertEqual(len(actual), len(expect))
        for f, (n, t) in zip(actual, expect):
            self.assert_field(f, n, t)

    def assert_field(self, field, name, type_):
        self.assertEqual(field.name, name)
        self.assertEqual(field.type, type_)

    def test_generate_interface_types(self):

        request_type, response_type = reqrep.generate_interface_types(
            TestInterface, 'Test'
        )
        args_type = request_type.Args

        self.assert_fields(
            dataclasses.fields(request_type),
            [('args', args_type)],
        )
        self.assert_fields(
            dataclasses.fields(args_type),
            [
                ('greet', typing.Optional[args_type.Greet]),
                ('square', typing.Optional[args_type.Square]),
                ('test_default', typing.Optional[args_type.TestDefault]),
            ],
        )
        self.assert_fields(
            dataclasses.fields(args_type.Greet),
            [('name', TestData)],
        )
        self.assert_fields(
            dataclasses.fields(args_type.Square),
            [('x', int)],
        )
        self.assert_fields(
            dataclasses.fields(args_type.TestDefault),
            [('s', str)],
        )

        self.assert_fields(
            dataclasses.fields(response_type),
            [
                ('result', typing.Optional[response_type.Result]),
                ('error', typing.Optional[response_type.Error]),
            ],
        )
        self.assert_fields(
            dataclasses.fields(response_type.Result),
            [
                ('greet', typing.Optional[None]),
                ('square', typing.Optional[int]),
                ('test_default', typing.Optional[None]),
            ],
        )
        self.assert_fields(
            dataclasses.fields(response_type.Error),
            [('exception', Exception)],
        )

        # Test default value.
        with self.assertRaisesRegex(TypeError, r'missing 1 .* \'name\''):
            request_type.Args.Greet()
        self.assertEqual(
            request_type.Args.TestDefault(),
            request_type.Args.TestDefault(s='hello world'),
        )

        self.assertEqual(
            response_type(),
            response_type(result=None, error=None),
        )

    def test_decorate_class(self):

        @reqrep.raising(ValueError)
        class Test1:
            pass

        @reqrep.raising(ValueError)
        class Test2:
            x: int

        @dataclasses.dataclass
        @reqrep.raising(ValueError)
        class Test3:
            x: int

        self.assertFalse(hasattr(Test1, '__annotations__'))
        # pylint: disable=no-member
        self.assertEqual(Test2.__annotations__, {'x': int})
        self.assertEqual(Test3.__annotations__, {'x': int})
        # pylint: enable=no-member

        for type_ in (Test1, Test2, Test3):
            self.assertEqual(
                reqrep.get_interface_metadata(type_),
                reqrep.Metadata(raising=(ValueError, )),
            )

        _, response_type = reqrep.generate_interface_types(Test1)
        self.assert_fields(
            dataclasses.fields(response_type),
            [
                ('result', typing.Optional[response_type.Result]),
                ('error', typing.Optional[response_type.Error]),
            ],
        )
        self.assert_fields(dataclasses.fields(response_type.Result), [])
        self.assert_fields(
            dataclasses.fields(response_type.Error),
            [('value_error', ValueError)],
        )


if __name__ == '__main__':
    unittest.main()
