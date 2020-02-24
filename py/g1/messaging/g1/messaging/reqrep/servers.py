__all__ = [
    'Server',
]

import contextlib
import dataclasses
import logging

import nng
import nng.asyncs

from g1.bases import classes
from g1.bases import typings
from g1.bases.assertions import ASSERT

from . import utils

LOG = logging.getLogger(__name__)


class Server:
    """Expose an (asynchronous) application object on a socket.

    This is a fairly simple server for providing remote method calls.

    If application defines context management (i.e., ``__enter__``), it
    will be called when server's context management is called.  This
    provides some sorts of server start/stop callbacks to application.
    """

    def __init__(
        self,
        application,
        request_type,
        response_type,
        wiredata,
        *,
        warning_level_exc_types=(),
        invalid_request_error=None,
        internal_server_error=None,
    ):
        self._application = application
        self._request_type = request_type
        self._response_type = response_type
        self._wiredata = wiredata
        self._warning_level_exc_types = frozenset(warning_level_exc_types)
        # When there is only one error type, reqrep.make_annotations
        # would not generate Optional[T].
        fields = dataclasses.fields(self._response_type.Error)
        if len(fields) == 1:
            self._declared_error_types = {
                ASSERT.issubclass(fields[0].type, Exception): fields[0].name
            }
        else:
            self._declared_error_types = {
                ASSERT(
                    typings.is_recursive_type(field.type)
                    and typings.is_union_type(field.type)
                    and typings.match_optional_type(field.type),
                    'expect typing.Optional[T]: {!r}',
                    field,
                ): field.name
                for field in fields
            }
        self._stack = None
        # For convenience, create socket before ``__enter__``.
        self.socket = nng.asyncs.Socket(nng.Protocols.REP0)
        # Prepared errors.
        self._invalid_request_error_wire = self._lower_error_or_none(
            invalid_request_error
        )
        self._internal_server_error_wire = self._lower_error_or_none(
            internal_server_error
        )

    def _lower_error_or_none(self, error):
        if error is None:
            return None
        ASSERT.isinstance(error, Exception)
        error_name = ASSERT(
            self._match_error_type(error), 'unknown error type: {!r}', error
        )
        return self._wiredata.to_lower(
            self._response_type(
                error=self._response_type.Error(**{error_name: error})
            )
        )

    def _match_error_type(self, error):
        # NOTE: We match the exact type rather than calling isinstance
        # because error types could form a hierarchy, and isinstance
        # might match a parent error type rather than a child type.
        return self._declared_error_types.get(type(error))

    __repr__ = classes.make_repr('{self.socket!r}')

    def __enter__(self):
        ASSERT.none(self._stack)
        with contextlib.ExitStack() as stack:
            stack.enter_context(self.socket)
            if hasattr(self._application, '__enter__'):
                stack.enter_context(self._application)
            self._stack = stack.pop_all()
        return self

    def __exit__(self, *args):
        return self._stack.__exit__(*args)

    async def serve(self):
        """Serve requests sequentially.

        To serve requests concurrently, just spawn multiple tasks
        running this.
        """
        LOG.info('start server: %r', self)
        try:
            with nng.asyncs.Context(ASSERT.not_none(self.socket)) as context:
                while True:
                    response = await self._serve(await context.recv())
                    if response is not None:
                        await context.send(response)
        except nng.Errors.ECLOSED:
            pass
        LOG.info('stop server: %r', self)

    def shutdown(self):
        self.socket.close()

    async def _serve(self, request):

        LOG.debug('wire request: %r', request)

        try:
            request = self._wiredata.to_upper(self._request_type, request)
        except Exception:
            LOG.warning('to_upper error: %r', request, exc_info=True)
            return self._invalid_request_error_wire

        try:
            method_name, method_args = utils.select(request.args)
        except Exception:
            LOG.warning('invalid request: %r', request, exc_info=True)
            return self._invalid_request_error_wire

        try:
            method = getattr(self._application, method_name)
        except AttributeError:
            LOG.warning('unknown method: %s: %r', method_name, request)
            return self._invalid_request_error_wire

        try:
            result = await method(
                **{
                    field.name: getattr(method_args, field.name)
                    for field in dataclasses.fields(method_args)
                }
            )
        except Exception as exc:
            if type(exc) in self._warning_level_exc_types:  # pylint: disable=unidiomatic-typecheck
                log = LOG.warning
            else:
                log = LOG.error
            log('server error: %r', request, exc_info=True)
            response = self._make_error_response(exc)
            if response is None:
                return self._internal_server_error_wire
        else:
            response = self._response_type(
                result=self._response_type.Result(**{method_name: result})
            )

        try:
            response = self._wiredata.to_lower(response)
        except Exception:
            # It should be an error when a response object that is fully
            # under our control cannot be lowered correctly.
            LOG.exception('to_lower error: %r, %r', request, response)
            return self._internal_server_error_wire
        LOG.debug('wire response: %r', response)

        return response

    def _make_error_response(self, error):
        error_name = self._match_error_type(error)
        if error_name is None:
            return None
        return self._response_type(
            error=self._response_type.Error(**{error_name: error})
        )
