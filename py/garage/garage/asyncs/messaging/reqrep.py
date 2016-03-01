__all__ = [
    'client',
    'server',
]

import asyncio
import logging
from functools import partial

from garage import asserts
from garage.asyncs import utils
from garage.asyncs.futures import awaiting, one_of
from garage.asyncs.processes import process

import nanomsg as nn
from nanomsg.asyncio import Socket


LOG = logging.getLogger(__name__)


@process
async def client(inbox, service_url, *, timeout=None):

    def close_inbox(inbox):
        num_reqs = len(inbox.close(graceful=False))
        if num_reqs:
            LOG.warning('client: drop %d requests', num_reqs)
        # The "producer" side of a future object should not cancel it.

    async with awaiting.callback(partial(close_inbox, inbox)), \
               Socket(protocol=nn.NN_REQ) as sock:
        sock.connect(service_url)

        while not inbox.is_closed():

            # XXX Wrap inbox.get() in an asyncio.ensure_future() call so
            # that we may yield to the event loop?  This is strange.
            request, response_fut = await asyncio.ensure_future(inbox.get())

            stop = asyncio.ensure_future(inbox.until_closed())
            timer = asyncio.ensure_future(utils.timer(timeout))

            response = None
            try:
                asserts.precond(isinstance(request, bytes))
                await one_of([sock.send(request)], [stop, timer])
                with await one_of([sock.recv()], [stop, timer]) as message:
                    response = bytes(message.as_memoryview())

            except Exception as exc:
                if response_fut.cancelled():
                    LOG.exception(
                        'client: request errs while response_fut cancelled: '
                        'request=%r response=%r',
                        request, response)
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

            finally:
                stop.cancel()
                timer.cancel()


@process
async def server(inbox, service_url, *,
                 timeout=None,
                 timeout_response=None):

    # NOTE: server() _write_ to instead of read from its inbox.

    asserts.precond(timeout_response is None or
                    isinstance(timeout_response, bytes))

    def close_inbox(inbox):
        reqreps = inbox.close(graceful=False)
        if reqreps:
            LOG.warning('server: drop %d requests', len(reqreps))
        # The "consumer" side of a future object is responsible for
        # canceling it.
        for _, rep_fut in reqreps:
            rep_fut.cancel()

    async with awaiting.callback(partial(close_inbox, inbox)), \
               Socket(protocol=nn.NN_REP) as sock:
        sock.bind(service_url)

        while not inbox.is_closed():

            with await one_of([sock.recv(), inbox.until_closed()]) as message:
                request = bytes(message.as_memoryview())

            response_fut = asyncio.Future()
            await inbox.put((request, response_fut))

            try:
                response = await one_of(
                    [response_fut, inbox.until_closed()],
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                if timeout_response is None:
                    raise
                LOG.warning('request timeout %f', timeout, exc_info=True)
                response = timeout_response
            asserts.postcond(isinstance(response, bytes))

            await one_of([sock.send(response), inbox.until_closed()])
