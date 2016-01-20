__all__ = [
    'ClientBase',
    'InterfaceSpec',
    'validate_request',
]

from collections import namedtuple
from functools import partialmethod

from garage import asserts

from . import remote_call as _remote_call


InterfaceSpec = namedtuple('InterfaceSpec', '''
    method request_types response_type errno_type
''')


class ClientMeta(type):

    def __new__(mcs, name, bases, namespace, interface_specs=None):
        if interface_specs:
            for spec in interface_specs:
                asserts.precond(spec.method not in namespace)
                namespace[spec.method] = partialmethod(
                    ClientBase.remote_call,
                    spec.method,
                    spec.request_types,
                    spec.response_type,
                    spec.errno_type,
                )
        return super().__new__(mcs, name, bases, namespace)

    def __init__(cls, name, bases, namespace, **_):
        super().__init__(name, bases, namespace)


class ClientBase(metaclass=ClientMeta):

    def __init__(self, sock):
        self.__sock = sock

    async def remote_call(
            self, method, request_types, response_type, errno_type,
            **request):
        asserts.precond(
            validate_request(request_types, request), '%r', request)
        response, errno = await _remote_call(self.__sock, method, request)
        if response is not None:
            response = response_type(response)
        if errno is not None:
            errno = errno_type(errno)
        return response, errno


def validate_request(request_types, request):
    return (
        len(request_types) == len(request) and
        all(key in request_types and isinstance(value, request_types[key])
            for key, value in request.items())
    )
