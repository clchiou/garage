__all__ = [
    'Terminated',
    'Unavailable',
    'client',
    'client_supervisor',
    'server',
    # TODO: Implement server_supervisor.
]

import logging

from curio import TaskTimeout, timeout_after

import nanomsg

from garage import asyncs
from garage.asyncs import queues
from garage.asyncs.futures import Future


LOG = logging.getLogger(__name__)


class Terminated(Exception):
    """Client agent is terminated."""


class Unavailable(Exception):
    """Service is unavailable."""


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

    def transform_error(exc):
        if isinstance(exc, TaskTimeout):
            new_exc = Unavailable()
            new_exc.__cause__ = exc
            return new_exc
        elif isinstance(exc, nanomsg.EBADF):
            new_exc = Terminated()
            new_exc.__cause__ = exc
            return new_exc
        else:
            return exc

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
            async with timeout_after(timeout):
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
                response_promise.set_exception(transform_error(exc))

        else:
            response_promise.set_result(response)

    LOG.info('client: exit')


async def server(socket, request_queue, *, timeout=None, error_handler=None):
    """Act as server-side in the reqrep protocol.

    NOTE: error_handler is not asynchronous because you should probably
    send back error messages without being blocked indefinitely.
    """

    if error_handler is None:
        error_handler = lambda *_: None

    LOG.info('server: start receiving requests')
    while True:

        with await socket.recv() as message:
            request = bytes(message.as_memoryview())

        try:
            async with timeout_after(timeout), Future() as response_future:
                promise = response_future.promise()
                try:
                    await request_queue.put((request, promise))
                except queues.Closed:
                    break
                response = await response_future.result()

        except Exception as exc:
            error_response = error_handler(request, exc)
            if error_response is None:
                raise
            LOG.exception('server: err when processing request: %r', request)
            await socket.send(error_response)

        else:
            await socket.send(response)

    LOG.info('server: exit')
