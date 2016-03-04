__all__ = [
    'client',
    'server',
]

import asyncio
import logging

from garage import asserts
from garage.asyncs import utils
from garage.asyncs.futures import one_of
from garage.asyncs.processes import process

import nanomsg as nn
from nanomsg.asyncio import Socket


LOG = logging.getLogger(__name__)


@process
async def client(exit, service_url, request_queue, *, timeout=None):

    async def main(sock):
        request, response_fut = await one_of([request_queue.get()], [exit])
        timer = asyncio.ensure_future(utils.timer(timeout))
        await on_response(
            one_of([transmit(sock, request), timer], [exit]),
            request, response_fut,
        )

    async def transmit(sock, request):
        asserts.precond(isinstance(request, bytes))
        await sock.send(request)
        with await sock.recv() as message:
            return bytes(message.as_memoryview())

    async def on_response(transmit_fut, request, response_fut):
        try:
            response = await transmit_fut
        except Exception as exc:
            if response_fut.cancelled():
                LOG.exception(
                    'client: request errs while response_fut cancelled: '
                    'request=%r',
                    request)
            else:
                response_fut.set_exception(exc)
        else:
            if response_fut.cancelled():
                LOG.warning(
                    'client: drop response: request=%r response=%r',
                    request, response)
            else:
                asserts.postcond(response is not None)
                response_fut.set_result(response)

    with Socket(protocol=nn.NN_REQ) as sock:
        sock.connect(service_url)
        while True:
            await main(sock)


@process
async def server(exit, service_url, request_queue, *,
                 timeout=None,
                 timeout_response=None):
    asserts.precond(timeout_response is None or
                    isinstance(timeout_response, bytes))

    async def serve_one(request, response_fut):
        await request_queue.put((request, response_fut))
        response = await response_fut
        asserts.postcond(isinstance(response, bytes))
        return response

    with Socket(protocol=nn.NN_REP) as sock:
        sock.bind(service_url)
        while True:
            with await one_of([sock.recv()], [exit]) as message:
                request = bytes(message.as_memoryview())
            response_fut = asyncio.Future()
            try:
                response = await one_of(
                    [serve_one(request, response_fut)],
                    [exit],
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                if timeout_response is None:
                    raise
                LOG.warning('request timeout %f', timeout, exc_info=True)
                response = timeout_response
            finally:
                response_fut.cancel()
            await one_of([sock.send(response)], [exit])
