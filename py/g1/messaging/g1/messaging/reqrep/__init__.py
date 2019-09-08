"""Generate request/response type pair from an interface type.

Given this interface type:

    @g1.messaging.reqrep.raising(SpamError)
    class Foo:

        def func_bar(self, x: int) -> float:
            raise NotImplementedError

        def func_baz(self, s: str) -> bytes:
            raise NotImplementedError

It will generate these types:

    @dataclasses.dataclass(frozen=True)
    class FooRequest:

        @dataclasses.dataclass(frozen=True)
        class Args:

            @dataclasses.dataclass(frozen=True)
            class FuncBar:
                x: int

            @dataclasses.dataclass(frozen=True)
            class FuncBaz:
                s: str

            func_bar: typing.Optional[FuncBar] = None
            func_baz: typing.Optional[FuncBaz] = None

        args: Args

        types = g1.bases.collections.Namespace(
            func_bar=Args.FuncBar,
            func_baz=Args.FuncBaz,
        )

        m = g1.bases.collections.Namespace(
            func_bar=...,
            func_baz=...,
        )

    @dataclasses.dataclass(frozen=True)
    class FooResponse:

        @dataclasses.dataclass(frozen=True)
        class Result:
            func_bar: typing.Optional[float] = None
            func_baz: typing.Optional[bytes] = None

        @dataclasses.dataclass(frozen=True)
        class Error:
            spam_error: typing.Optional[SomeError] = None

        result: typing.Optional[Result] = None
        error: typing.Optional[Error] = None
"""

__all__ = [
    'generate_interface_types',
    'raising',
    # Interface metadata.
    'get_interface_metadata',
    'set_interface_metadata',
]

import dataclasses
import inspect
import typing

from g1.bases import cases
from g1.bases import classes
from g1.bases import collections
from g1.bases.assertions import ASSERT

from .. import metadata

# Use module path as metadata key.
METADATA_KEY = __name__


@dataclasses.dataclass(frozen=True)
class Metadata:
    raising: typing.Tuple[Exception, ...]


def get_interface_metadata(cls, default=None):
    """Get metadata of a interface type."""
    return metadata.get_metadata(cls, METADATA_KEY, default)


def set_interface_metadata(cls, md):
    """Set metadata of a interface type."""
    metadata.set_metadata(cls, METADATA_KEY, md)


def raising(*exc_types):
    """Annotate a class or a method about what exceptions it raises."""

    ASSERT.all(exc_types, lambda type_: issubclass(type_, Exception))

    def decorate(cls_or_func):
        md = get_interface_metadata(cls_or_func)
        if md:
            md = Metadata(raising=md.raising + exc_types)
        else:
            md = Metadata(raising=exc_types)
        set_interface_metadata(cls_or_func, md)
        return cls_or_func

    return decorate


@dataclasses.dataclass(frozen=True)
class MethodSignature:
    parameters: typing.List[typing.Tuple[str, type]]
    defaults: typing.Mapping[str, typing.Any]
    return_type: typing.Optional[type]
    raising: typing.List[Exception]

    @classmethod
    def from_method(cls, method):

        signature = inspect.signature(method)

        parameters = [ \
            (parameter.name, parameter.annotation)
            for parameter in signature.parameters.values()
            if parameter.annotation is not parameter.empty
        ]

        defaults = {
            parameter.name: parameter.default
            for parameter in signature.parameters.values()
            if parameter.default is not parameter.empty
        }

        # We treat ``None``-annotation the same as no annotation.
        if signature.return_annotation is not signature.empty:
            return_type = signature.return_annotation
        else:
            return_type = None

        md = get_interface_metadata(method)
        raising_ = md.raising if md else ()

        return cls(
            parameters=parameters,
            defaults=defaults,
            return_type=return_type,
            raising=raising_,
        )


def generate_interface_types(interface, name=None):
    """Generate request and response type for the given interface."""

    if not isinstance(interface, type):
        interface = type(interface)

    module = interface.__module__

    method_signatures = {
        name: MethodSignature.from_method(getattr(interface, name))
        for name in classes.get_public_method_names(interface)
    }

    args_type, types, makers = make_args_type(module, method_signatures)
    request_type = dataclasses.make_dataclass(
        (name or interface.__name__) + 'Request',
        [('args', args_type)],
        namespace={
            'Args': args_type,
            'types': types,
            'm': makers,
        },
        frozen=True,
    )
    request_type.__module__ = module

    result_type = make_result_type(module, method_signatures)
    error_type = make_error_type(module, interface, method_signatures)
    response_type = dataclasses.make_dataclass(
        (name or interface.__name__) + 'Response',
        [
            (
                'result',
                typing.Optional[result_type],
                dataclasses.field(default=None),
            ),
            (
                'error',
                typing.Optional[error_type],
                dataclasses.field(default=None),
            ),
        ],
        namespace={
            'Result': result_type,
            'Error': error_type,
        },
        frozen=True,
    )
    response_type.__module__ = module

    return request_type, response_type


def make_args_type(module, method_signatures):

    method_args_types = {
        name: make_method_args_type(module, name, signature)
        for name, signature in method_signatures.items()
    }

    args_type = dataclasses.make_dataclass(
        'Args',
        make_annotations(list(method_args_types.items())),
        namespace={
            type_.__name__: type_
            for type_ in method_args_types.values()
        },
        frozen=True,
    )
    args_type.__module__ = module

    types = collections.Namespace(**method_args_types)

    makers = collections.Namespace(
        **{
            name: _make_args_maker(args_type, name, type_)
            for name, type_ in method_args_types.items()
        },
    )

    return args_type, types, makers


def _make_args_maker(args_type, name, type_):

    def make(**kwargs):
        return args_type(**{name: type_(**kwargs)})

    return make


def make_method_args_type(module, method_name, signature):
    method_args_type = dataclasses.make_dataclass(
        cases.lower_snake_to_upper_camel(method_name),
        [(name, type_) if name not in signature.defaults else
         (name, type_, dataclasses.field(default=signature.defaults[name]))
         for name, type_ in signature.parameters],
        frozen=True,
    )
    method_args_type.__module__ = module
    return method_args_type


def make_result_type(module, method_signatures):
    result_type = dataclasses.make_dataclass(
        'Result',
        make_annotations([(name, signature.return_type)
                          for name, signature in method_signatures.items()]),
        frozen=True
    )
    result_type.__module__ = module
    return result_type


def make_error_type(module, interface, method_signatures):
    md = get_interface_metadata(interface)
    types = set(md.raising if md else ())
    for signature in method_signatures.values():
        types.update(signature.raising)
    error_type = dataclasses.make_dataclass(
        'Error',
        make_annotations([
            (cases.camel_to_lower_snake(type_.__name__), type_)
            for type_ in sorted(types, key=lambda type_: type_.__name__)
        ]),
        frozen=True,
    )
    error_type.__module__ = module
    return error_type


def make_annotations(names_and_types):
    if len(names_and_types) == 1:
        # When there is only one method, don't declare as optional.
        return names_and_types
    else:
        return [
            (name, typing.Optional[type_], dataclasses.field(default=None))
            for name, type_ in names_and_types
        ]
