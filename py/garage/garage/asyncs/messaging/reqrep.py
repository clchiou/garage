__all__ = [
    'Terminated',
    'Unavailable',
    'client',
    'client_supervisor',
    'server',
    'server_supervisor',
]

import logging

import curio

import nanomsg

from garage import asyncs
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
    elif isinstance(exc, nanomsg.EBADF):
        new_exc = Terminated()
        new_exc.__cause__ = exc
        return new_exc
    else:
        return exc


async def client_supervisor(
    graceful_exit, socket, request_queue, *, timeout=None):

    async def cleanup():
        """Wait for the graceful exit event and then clean up itself.

        It will:
        * Close socket so that the client task will not send any further
          requests.
        * Close the queue so that upstream will not enqueue any further
          requests.

        The requests still in the queue will be "processed", with their
        result being set to EBADF, since the socket is closed.  This
        signals (and unblocks) all blocked upstream tasks.
        """
        try:
            await graceful_exit.wait()
        finally:
            # Use 'finally' to close them even on cancellation.
            socket.close()
            request_queue.close()

    async with await asyncs.cancelling.spawn(cleanup):
        coro = client(socket, request_queue, timeout=timeout)
        async with await asyncs.cancelling.spawn(coro) as client_task:
            await client_task.join()


async def client(socket, request_queue, *, timeout=None):
    """Act as client-side in the reqrep protocol."""

    LOG.info('client: start sending requests')
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

    LOG.info('client: exit')


async def server_supervisor(
    graceful_exit, socket, request_queue, *, timeout=None, error_handler=None):

    async def cleanup():
        """Wait for the graceful exit event and then clean up itself.

        It will:
        * Close socket so that the server task will not recv or send any
          further requests.
        * Close the queue so that downstream will not dequeue any
          request.

        The requests still in the queue will be dropped (since socket is
        closed, their response cannot be sent back to the client).
        """
        try:
            await graceful_exit.wait()
        finally:
            # Use 'finally' to close them even on cancellation.
            socket.close()
            num_dropped = len(request_queue.close(graceful=False))
            if num_dropped:
                LOG.info('server_supervisor: drop %d requests', num_dropped)

    async with await asyncs.cancelling.spawn(cleanup):
        coro = server(
            socket, request_queue,
            timeout=timeout,
            error_handler=error_handler,
        )
        async with await asyncs.cancelling.spawn(coro) as server_task:
            await server_task.join()


async def server(socket, request_queue, *, timeout=None, error_handler=None):
    """Act as server-side in the reqrep protocol.

    NOTE: error_handler is not asynchronous because you should probably
    send back error messages without being blocked indefinitely.
    """

    if error_handler is None:
        error_handler = lambda *_: None

    LOG.info('server: start receiving requests')
    while True:

        try:
            with await socket.recv() as message:
                request = bytes(message.as_memoryview())
        except nanomsg.EBADF:
            break

        try:
            async with curio.timeout_after(timeout):
                async with futures.Future() as response_future:
                    try:
                        await request_queue.put((
                            request,
                            response_future.promise(),
                        ))
                    except queues.Closed:
                        LOG.debug('server: drop request: %r', request)
                        break
                    response = await response_future.result()

        except Exception as exc:
            response = error_handler(request, _transform_error(exc))
            if response is None:
                raise
            LOG.exception('server: err when processing request: %r', request)

        try:
            await socket.send(response)
        except nanomsg.EBADF:
            LOG.debug('server: drop response: %r, %r', request, response)
            break

    LOG.info('server: exit')
