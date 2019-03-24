import unittest

import dataclasses
import inspect
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


class TestNameConflict:

    def request(self, x: int):
        raise NotImplementedError

    def f(self, x: int, y: int):
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

    def assert_field(self, field, name, type_):
        self.assertEqual(field.name, name)
        self.assertEqual(field.type, type_)

    def test_generate_interface_types(self):

        request_type, response_type = reqrep.generate_interface_types(
            TestInterface, 'Test'
        )

        self.assertEqual(
            sorted(request_type._types),
            ['greet', 'square', 'test_default'],
        )
        fields = dataclasses.fields(request_type)
        anno = typing.Union[ \
            request_type._types.square,
            request_type._types.greet,
            request_type._types.test_default,
        ]
        self.assertEqual(request_type.__name__, 'TestRequest')
        self.assertEqual(request_type.__annotations__, {'request': anno})
        self.assertEqual(len(fields), 1)
        self.assert_field(fields[0], 'request', anno)

        self.assertEqual(
            request_type.square(x=1),
            request_type(request=request_type._types.square(x=1)),
        )
        self.assertEqual(
            request_type.greet(name=TestData(name='world')),
            request_type(
                request=request_type._types.greet(name=TestData(name='world'))
            ),
        )

        # Test default value.
        with self.assertRaisesRegex(TypeError, r'missing 1 .* \'name\''):
            request_type.greet()
        self.assertEqual(
            request_type.test_default(),
            request_type(
                request=request_type._types.test_default(s='hello world')
            ),
        )

        fields = dataclasses.fields(response_type)
        self.assertEqual(response_type.__name__, 'TestResponse')
        self.assertEqual(
            response_type.__annotations__,
            {
                'result': typing.Union[None, int],
                'error': typing.Union[None, Exception],
            },
        )
        self.assertEqual(len(fields), 2)
        self.assert_field(fields[0], 'result', typing.Union[None, int])
        self.assert_field(fields[1], 'error', typing.Union[None, Exception])

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
        self.assertEqual(
            response_type.__annotations__,
            {
                'result': type(None),
                'error': typing.Union[None, ValueError],
            },
        )

    def test_name_conflict(self):
        """Test name conflict.

        Since ``generate_interface_types`` generates ``request`` field
        without default value, we may have a method also named "request"
        with no problem.
        """

        request_type, _ = reqrep.generate_interface_types(TestNameConflict)

        self.assertTrue(dataclasses.is_dataclass(request_type._types.request))
        self.assertTrue(inspect.ismethod(request_type.request))

        self.assertEqual(sorted(request_type._types), ['f', 'request'])
        fields = dataclasses.fields(request_type)
        anno = typing.Union[ \
            request_type._types.request,
            request_type._types.f,
        ]
        self.assertEqual(request_type.__name__, 'TestNameConflictRequest')
        self.assertEqual(request_type.__annotations__, {'request': anno})
        self.assertEqual(len(fields), 1)
        self.assert_field(fields[0], 'request', anno)

        self.assertEqual(
            request_type.request(x=1),
            request_type(request=request_type._types.request(x=1)),
        )


if __name__ == '__main__':
    unittest.main()
