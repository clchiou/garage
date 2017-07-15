__all__ = [
    'client',
    'server',
]

import logging

from curio import timeout_after

from garage.asyncs.futures import Future
from garage.asyncs import queues


LOG = logging.getLogger(__name__)


async def client(socket, request_queue, *, timeout=None):
    """Take requests from a request queue and send them to a
       nanomsg.NN_REQ socket.
    """

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
                    'client: err but request is cancelled: %r', request)
            response_promise.set_exception(exc)

        else:
            response_promise.set_result(response)

    LOG.info('client: exit')


async def server(socket, request_queue, *, timeout=None, error_handler=None):
    """Receive requests from a nanomsg.NN_REP socket and put them into a
       request queue.

       Note: error_handler is not asynchronous because you should
       probably send back error messages to clients without being
       blocked indefinitely.
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
