__all__ = [
    'Server',
]

import contextlib
import dataclasses
import logging

import nng
import nng.asyncs

from g1.bases import classes
from g1.bases.assertions import ASSERT

LOG = logging.getLogger(__name__)


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
        self._invalid_request_error_wire = None
        self._internal_server_error = None
        self._internal_server_error_wire = None

        self._stack = None
        self.socket = None

    def _set_error(self, name, error):
        if isinstance(error, type):
            error = error()
        ASSERT.isinstance(error, Exception)
        wire_error = self._wiredata.to_lower(self._response_type(error=error))
        setattr(self, name, error)
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
        ASSERT.none(self.socket)
        with contextlib.ExitStack() as stack:
            socket = stack.enter_context(nng.asyncs.Socket(nng.Protocols.REP0))
            if hasattr(self._application, '__enter__'):
                stack.enter_context(self._application)
            self._stack = stack.pop_all()
            self.socket = socket
        return self

    def __exit__(self, *args):
        stack, self._stack, self.socket = self._stack, None, None
        return stack.__exit__(*args)

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

        method_args = request.request

        method_name = type(method_args).__name__
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
            response = self._response_type(error=exc)
        else:
            response = self._response_type(result=result)

        try:
            response = self._wiredata.to_lower(response)
        except Exception:
            # It should be an error when a response object that is fully
            # under our control cannot be lowered correctly.
            LOG.exception('to_lower error: %r, %r', request, response)
            return self._internal_server_error_wire
        LOG.debug('wire response: %r', response)

        return response
