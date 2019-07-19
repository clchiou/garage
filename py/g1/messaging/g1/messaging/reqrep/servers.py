__all__ = [
    'Server',
    'run_server',
]

import contextlib
import dataclasses
import logging

import nng
import nng.asyncs

from g1.asyncs.bases import tasks
from g1.bases import classes
from g1.bases import typings
from g1.bases.assertions import ASSERT

from . import utils

LOG = logging.getLogger(__name__)


async def run_server(server, *, parallelism=1):
    ASSERT.greater(parallelism, 0)
    with server:
        if parallelism == 1:
            await server.serve()
        else:
            async with tasks.CompletionQueue() as queue:
                for _ in range(parallelism):
                    queue.spawn(server.serve)
                queue.close()
                async for task in queue:
                    task.get_result_nonblocking()


class Server:
    """Expose an (asynchronous) application object on a socket.

    This is a fairly simple server for providing remote method calls.

    If application defines context management (i.e., ``__enter__``), it
    will be called when server's context management is called.  This
    provides some sorts of server start/stop callbacks to application.
    """

    def __init__(self, application, request_type, response_type, wiredata):

        self._application = application
        self._request_type = request_type
        self._response_type = response_type
        self._wiredata = wiredata

        # Prepared errors.
        self._invalid_request_error = None
        self._invalid_request_error_name = None
        self._invalid_request_error_wire = None
        self._internal_server_error = None
        self._internal_server_error_name = None
        self._internal_server_error_wire = None

        self._error_types = {
            field.name: ASSERT(
                typings.is_recursive_type(field.type)
                and typings.is_union_type(field.type)
                and typings.match_optional_type(field.type),
                'expect typing.Optional[T]: {!r}',
                field,
            )
            for field in dataclasses.fields(self._response_type.Error)
        }

        self._stack = None
        # For convenience, create socket before ``__enter__``.
        self.socket = nng.asyncs.Socket(nng.Protocols.REP0)

    def _match_error_type(self, error):
        name = self._error_types.get(type(error))
        if name is not None:
            return name
        # Match error type the slow way.
        for name, error_type in self._error_types.items():
            if isinstance(error, error_type):
                return name
        return None

    def _set_error(self, name, error):
        ASSERT.isinstance(error, Exception)
        error_name = ASSERT(
            self._match_error_type(error), 'unknown error type: {!r}', error
        )
        wire_error = self._wiredata.to_lower(
            self._response_type(
                error=self._response_type.Error(**{error_name: error})
            )
        )
        setattr(self, name, error)
        setattr(self, name + '_name', error_name)
        setattr(self, name + '_wire', wire_error)

    invalid_request_error = property(
        lambda self: getattr(self, '_invalid_request_error'),
        lambda self, error: self._set_error('_invalid_request_error', error),
    )

    internal_server_error = property(
        lambda self: getattr(self, '_internal_server_error'),
        lambda self, error: self._set_error('_internal_server_error', error),
    )

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
            LOG.warning('server error: %r', request, exc_info=True)
            response = self._make_error_response(exc)
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
        if not error_name:
            LOG.warning('unknown error type: %r', error)
            ASSERT.true(self._internal_server_error)
            error_name = self._internal_server_error_name
            error = self._internal_server_error
        return self._response_type(
            error=self._response_type.Error(**{error_name: error})
        )
