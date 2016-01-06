import asyncio


class Barrier:

    def __init__(self, parties, *, loop=None):
        self.parties = parties
        self._cond = asyncio.Condition(loop=loop)

    async def wait(self):
        await self._cond.acquire()
        try:
            assert self.parties > 0
            self.parties -= 1
            if self.parties > 0:
                await self._cond.wait()
            else:
                self._cond.notify_all()
            assert self.parties == 0
        finally:
            self._cond.release()
