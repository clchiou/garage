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

from g1.bases import classes
from g1.bases import collections
from g1.bases.assertions import ASSERT
from g1.messaging import metadata

NoneType = type(None)

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

    method_names = classes.get_public_method_names(interface)

    method_signatures = {
        name: MethodSignature.from_method(getattr(interface, name))
        for name in method_names
    }

    method_args_types = {
        name: make_method_args_type(module, name, method_signatures[name])
        for name in method_names
    }

    if method_args_types:
        union_type = typing.Union[tuple(method_args_types.values())]
    else:
        # No method is declared; let's put a placeholder here.
        union_type = NoneType

    request_type = dataclasses.make_dataclass(
        (name or interface.__name__) + 'Request',
        [('request', union_type)],
        namespace={
            # Expose ``method_args_types`` for convenience.
            '_types': collections.Namespace(**method_args_types),
            **{
                name: bind_make_request(module, name, type_)
                for name, type_ in method_args_types.items()
            },
        },
        frozen=True,
    )
    request_type.__module__ = module

    response_type = dataclasses.make_dataclass(
        (name or interface.__name__) + 'Response',
        make_response_fields(interface, method_signatures),
        frozen=True,
    )
    response_type.__module__ = module

    return request_type, response_type


def make_method_args_type(module, method_name, signature):
    method_args_type = dataclasses.make_dataclass(
        method_name,
        [(name, type_) if name not in signature.defaults else
         (name, type_, dataclasses.field(default=signature.defaults[name]))
         for name, type_ in signature.parameters],
        frozen=True,
    )
    method_args_type.__module__ = module
    return method_args_type


def bind_make_request(module, method_name, method_args_type):

    def make_request(cls, **kwargs):
        return cls(request=method_args_type(**kwargs))

    make_request.__module__ = module
    make_request.__qualname__ = make_request.__name__ = method_name

    return classmethod(make_request)


def make_response_fields(interface, method_signatures):
    # Sadly ``typing`` does not support ``Either`` monad; so we make all
    # fields optional.
    fields = []

    result_types = set(
        signature.return_type
        for signature in method_signatures.values()
        if signature.return_type is not None
    )
    if result_types:
        result_types = typing.Optional[typing.Union[tuple(result_types)]]
    else:
        result_types = NoneType
    fields.append(('result', result_types, dataclasses.field(default=None)))

    md = get_interface_metadata(interface)
    error_types = set(md.raising if md else ())
    for signature in method_signatures.values():
        error_types.update(signature.raising)
    if error_types:
        error_types = typing.Optional[typing.Union[tuple(error_types)]]
    else:
        error_types = NoneType
    fields.append(('error', error_types, dataclasses.field(default=None)))

    return fields
