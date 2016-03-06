__all__ = [
    # Context manager helpers.
    'Ownership',
    'awaiting',
    'on_exit',
    # Future selectors.
    'each_completed',
    'each_of',
    'one_completed',
    'one_of',
]

import asyncio
import inspect
import logging


from garage import asserts


LOG = logging.getLogger(__name__)


class awaiting:
    """Wrap a asyncio.Future in an async context manager that awaits the
       future object at exit.  You may use this to enforce that child
       tasks do not outlive their parent task.
    """

    def __init__(self, future, *, cancel_on_exit=False, loop=None):
        self.future = asyncio.ensure_future(future, loop=loop)
        self.cancel_on_exit = cancel_on_exit

    async def __aenter__(self):
        return self.future

    async def __aexit__(self, *_):
        # Wait for the result if not done so yet.
        if not self.future.done():
            if self.cancel_on_exit:
                self.future.cancel()
            try:
                await self.future
            except Exception as exc:
                if not (self.cancel_on_exit and
                        isinstance(exc, asyncio.CancelledError)):
                    LOG.exception('error of %r', self.future)
            return

        # HACK: Retrieve the exception if not done so yet.
        if hasattr(self.future, '_log_traceback'):  # Python 3.4+
            retrieved = not self.future._log_traceback
        elif hasattr(self.future, '_tb_logger'):  # Python 3.3
            retrieved = not self.future._tb_logger
        else:
            retrieved = False  # Just to be safe...
        if not retrieved:
            exc = self.future.exception()
            if exc:
                LOG.error('error of %r', self.future, exc_info=exc)


class Ownership:
    """An async context manager that wraps a future object that you
       may replace with another future object.  When you replace,
       the old future object will be awaited.

       You may use this to implement task restart - the context
       manager represents the overall lifetime of tasks while each
       task may die and be replaced.
    """

    def __init__(self, *, cancel_on_exit=False, loop=None):
        self._context_manager = None
        self.cancel_on_exit = cancel_on_exit
        self.loop = loop

    async def __aenter__(self):
        asserts.precond(self._context_manager is None)
        return self

    async def __aexit__(self, *exc_info):
        mgr, self._context_manager = self._context_manager, None
        if mgr is not None:
            return await mgr.__aexit__(*exc_info)

    async def disown(self):
        mgr, self._context_manager = self._context_manager, None
        if mgr is not None:
            await mgr.__aexit__(None, None, None)
            return mgr.future

    def own(self, future):
        asserts.precond(self._context_manager is None)
        if future:
            self._context_manager = awaiting(
                future,
                cancel_on_exit=self.cancel_on_exit,
                loop=self.loop,
            )
            # NOTE: Not calling `await __aenter__()`.
            future = self._context_manager.future
            asserts.postcond(future is not None)
        return future


class on_exit:
    """Wrap an ordinary function or an awaitable in an async context
       manager which is called on exit.  If the function returns an
       awaitable, it will be awaited.
    """

    def __init__(self, callback):
        self.callback = callback

    async def __aenter__(self):
        return self.callback

    async def __aexit__(self, *_):
        if inspect.isawaitable(self.callback):
            await self.callback
        else:
            awaitable = self.callback()
            if inspect.isawaitable(awaitable):
                await awaitable


class each_completed:
    """A fancy wrapper of asyncio.wait() that takes a required and an
       optional set of futures and stops waiting after all required
       futures are done (some of the optional set futures might not be
       done yet).
    """

    def __init__(self, required, optional=(), *, timeout=None, loop=None):
        self.required = {
            asyncio.ensure_future(coro, loop=loop) for coro in required
        }
        self.optional = {
            asyncio.ensure_future(coro, loop=loop) for coro in optional
        }
        self.timeout = timeout
        self.loop = loop
        self._done = None

    async def __aiter__(self):
        return self

    async def __anext__(self):
        if self._done:
            return self._done.pop()
        if not self.required:
            raise StopAsyncIteration
        self._done, pending = await asyncio.wait(
            self.required | self.optional,
            timeout=self.timeout,
            loop=self.loop,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if not self._done:
            for fut in self.required:
                fut.cancel()
            raise asyncio.TimeoutError
        for fut in self._done:
            self.required.discard(fut)
            self.optional.discard(fut)
        return self._done.pop()


class each_of(each_completed):
    async def __anext__(self):
        return await (await super().__anext__())


async def one_completed(exclusive, extra=(), *, timeout=None, loop=None):
    """Return one completed future.  Other futures in `exclusive` set
       are cancelled if pending.
    """
    exclusive = [asyncio.ensure_future(fut, loop=loop) for fut in exclusive]
    extra = [asyncio.ensure_future(fut, loop=loop) for fut in extra]
    done, _ = await asyncio.wait(
        exclusive + extra,
        timeout=timeout,
        return_when=asyncio.FIRST_COMPLETED,
        loop=loop,
    )
    fut = done.pop() if done else None
    for other_fut in exclusive:
        if other_fut is fut:
            pass
        elif other_fut.done():
            exc = other_fut.exception()
            if exc:
                LOG.error('error in %r', other_fut, exc_info=exc)
        else:
            other_fut.cancel()
    if fut is None:
        raise asyncio.TimeoutError
    return fut


async def one_of(exclusive, extra=(), *, timeout=None, loop=None):
    return await (
        await one_completed(exclusive, extra, timeout=timeout, loop=loop))
