__all__ = [
    'InprocServer',
]

import functools

from g1.bases import collections as g1_collections

from . import utils


class InprocServer:
    """Expose an asynchronous application in the same process.

    This does not even use the inproc transport, omitting serialization
    and memory-copying of messages entirely.
    """

    def __init__(
        self,
        application,
        request_type,
        response_type,
        *,
        internal_server_error_type=None,
    ):
        self._application = application
        self._declared_error_types = frozenset(
            utils.get_declared_error_types(response_type)
        )
        self._internal_server_error_type = internal_server_error_type
        self.m = g1_collections.Namespace(
            **{
                name: self._make_transceiver(getattr(self._application, name))
                for name in request_type.m
            }
        )

    def __enter__(self):
        if hasattr(self._application, '__enter__'):
            self._application.__enter__()
        return self

    def __exit__(self, *args):
        if hasattr(self._application, '__exit__'):
            return self._application.__exit__(*args)
        return None

    def _make_transceiver(self, func):

        @functools.wraps(func)
        async def wrapper(**kwargs):
            return await self._transceive(func, kwargs)

        return wrapper

    async def _transceive(self, func, kwargs):
        try:
            return await func(**kwargs)
        except Exception as exc:
            if (
                self._internal_server_error_type is None
                or type(exc) in self._declared_error_types  # pylint: disable=unidiomatic-typecheck
            ):
                raise
            else:
                raise self._internal_server_error_type from exc
