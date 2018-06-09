__all__ = [
    'Terminated',
    'Unavailable',
    'client',
    'server',
]

import logging
import time

import curio

import nanomsg as nn

from garage import asyncs
from garage.assertions import ASSERT
from garage.asyncs import futures
from garage.asyncs import queues


LOG = logging.getLogger(__name__)


class Terminated(Exception):
    """Client agent is terminated."""


class Unavailable(Exception):
    """Service is unavailable."""


def _transform_error(exc):
    if isinstance(exc, curio.TaskTimeout):
        new_exc = Unavailable()
        new_exc.__cause__ = exc
        return new_exc
    elif isinstance(exc, (nn.EBADF, queues.Closed)):
        new_exc = Terminated()
        new_exc.__cause__ = exc
        return new_exc
    else:
        return exc


async def client(graceful_exit, sockets, request_queue, timeout=None):
    """Act as client-side in the reqrep protocol.

    NOTE: Because we want end-to-end functionality (non-raw sockets), a
    socket can only handle one request at a time; to overcome this, we
    use a pool of sockets.

    In additional to handling requests, this waits for the graceful exit
    event and then clean up itself.

    When cleaning up, it:
    * Close socket so that pump_requests will not send any further
      requests.
    * Close the queue so that upstream will not enqueue any further
      requests.

    The requests still in the queue will be "processed", with their
    result being set to EBADF, since the socket is closed.  This signals
    and unblocks all blocked upstream tasks.
    """

    for socket in sockets:
        ASSERT.equal(socket.options.nn_domain, nn.AF_SP)
        ASSERT.equal(socket.options.nn_protocol, nn.NN_REQ)

    async def pump_requests(socket):
        LOG.info('client: start sending requests to: %s', socket)
        while True:

            try:
                request, response_promise = await request_queue.get()
            except queues.Closed:
                break

            if not response_promise.set_running_or_notify_cancel():
                LOG.debug('client: drop request: %r', request)
                continue

            try:
                async with curio.timeout_after(timeout):
                    await socket.send(request)
                    with await socket.recv() as message:
                        response = bytes(message.as_memoryview())

            except Exception as exc:
                if response_promise.cancelled():
                    LOG.exception(
                        'client: err but request is cancelled: %r',
                        request,
                    )
                else:
                    response_promise.set_exception(_transform_error(exc))

            else:
                response_promise.set_result(response)

        LOG.info('client: stop sending requests to: %s', socket)

    async with asyncs.TaskStack() as stack:
        for socket in sockets:
            await stack.spawn(pump_requests(socket))
        stack.sync_callback(request_queue.close)
        for socket in sockets:
            stack.sync_callback(socket.close)
        await stack.spawn(graceful_exit.wait())
        await (await stack.wait_any()).join()


async def server(
    graceful_exit, socket, request_queue, timeout=None, error_handler=None):

    """Act as server-side in the reqrep protocol.

    NOTE: error_handler is not asynchronous because you should probably
    send back error messages without being blocked indefinitely.

    In additional to handling requests, this waits for the graceful exit
    event and then clean up itself.

    When cleaning up, it:
    * Close socket so that the pump_requests will not recv new requests
      and will exit.
    * Close the queue so that downstream will not dequeue any request.

    The requests still in the queue will be dropped (since socket is
    closed, their response cannot be sent back to the client).
    """

    ASSERT.equal(socket.options.nn_domain, nn.AF_SP_RAW)
    ASSERT.equal(socket.options.nn_protocol, nn.NN_REP)

    if error_handler is None:
        error_handler = lambda *_: None

    async def pump_requests(handlers):
        LOG.info('server: start receiving requests from: %s', socket)
        while True:

            try:
                message = await socket.recvmsg()
            except nn.EBADF:
                break
            with message:
                response_message = nn.Message()
                # NOTE: It is important to set control header in the
                # response message from the request so that response can
                # be correctly routed back to the right sender.
                response_message.adopt_control(*message.disown_control())
                request = bytes(message.as_memoryview())

            # Enqueue request here rather than in handle_request so that
            # pump_requests may apply back pressure to socket.
            begin_time = time.perf_counter()
            try:
                response_future = futures.Future()
                async with curio.timeout_after(timeout):
                    await request_queue.put((
                        request,
                        response_future.promise(),
                    ))
            except Exception as exc:
                await on_error(exc, request, response_message)
                continue

            await handlers.spawn(handle_request(
                begin_time,
                request,
                response_future,
                response_message,
            ))

        LOG.info('server: stop receiving requests from: %s', socket)

    async def handle_request(
        begin_time, request, response_future, response_message):

        if timeout is not None:
            remaining_time = timeout - (time.perf_counter() - begin_time)
            if remaining_time <= 0:
                response_future.cancel()
                await on_error(
                    Unavailable(), request, response_message,
                    exc_info=False,
                )
                return
        else:
            remaining_time = None

        try:
            async with curio.timeout_after(remaining_time), response_future:
                response = await response_future.result()
        except Exception as exc:
            await on_error(exc, request, response_message)
        else:
            await send_response(request, response, response_message)

    async def on_error(exc, request, response_message, *, exc_info=True):
        LOG.error(
            'server: err when processing request: %r',
            request, exc_info=exc_info,
        )
        error_response = error_handler(request, _transform_error(exc))
        if error_response is not None:
            await send_response(request, error_response, response_message)

    async def send_response(request, response, response_message):
        response_message.adopt_message(response, len(response), False)
        try:
            await socket.sendmsg(response_message)
        except nn.EBADF:
            LOG.debug('server: drop response: %r, %r', request, response)

    async def join_handlers(handlers):
        async for handler in handlers:
            if handler.exception:
                LOG.error(
                    'server: err in request handler',
                    exc_info=handler.exception,
                )

    def close_queue():
        num_dropped = len(request_queue.close(graceful=False))
        if num_dropped:
            LOG.info('server: drop %d requests', num_dropped)

    async with asyncs.TaskSet() as handlers, asyncs.TaskStack() as stack:
        await stack.spawn(join_handlers(handlers))
        await stack.spawn(pump_requests(handlers))
        stack.sync_callback(close_queue)
        stack.sync_callback(socket.close)
        await stack.spawn(graceful_exit.wait())
        await (await stack.wait_any()).join()
