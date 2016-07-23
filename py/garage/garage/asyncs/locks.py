"""Synchronization primitives."""

__all__ = [
    'ReadWriteLock',
]

from asyncio.locks import (
    _ContextManagerMixin,
    Condition,
)


class ReadWriteLock:

    class _State:

        def __init__(self, *, loop=None):
            self.num_readers = 0
            self.num_writers = 0
            # Condition: num_writers == 0.
            self.cond_nwz = Condition(loop=loop)
            # Condition: num_readers == num_writers == 0.
            self.cond_nrnwz = Condition(loop=loop)

    class ReadLock(_ContextManagerMixin):

        def __init__(self, state):
            self.state = state

        def locked(self):
            return not self._nwz()

        def _nwz(self):
            return self.state.num_writers == 0

        async def acquire(self):
            async with self.state.cond_nwz:
                if not self._nwz():
                    await self.state.cond_nwz.wait_for(self._nwz)
                self.state.num_readers += 1
                return True

        def release(self):
            if self.state.num_readers == 0:
                raise RuntimeError('ReadLock is not acquired')
            assert self.state.num_writers == 0
            self.state.num_readers -= 1
            if self.state.num_readers == 0 and self.state.cond_nrnwz.locked():
                self.state.cond_nrnwz.notify()

    class WriteLock(_ContextManagerMixin):

        def __init__(self, state):
            self.state = state

        def locked(self):
            return not self._nrnwz()

        def _nrnwz(self):
            return self.state.num_readers == 0 and self.state.num_writers == 0

        async def acquire(self):
            async with self.state.cond_nrnwz:
                if not self._nrnwz():
                    await self.state.cond_nrnwz.wait_for(self._nrnwz)
                self.state.num_writers += 1
                return True

        def release(self):
            if self.state.num_writers == 0:
                raise RuntimeError('WriteLock is not acquired')
            assert self.state.num_readers == 0
            assert self.state.num_writers == 1
            self.state.num_writers = 0
            if self.state.cond_nwz.locked():
                self.state.cond_nwz.notify_all()
            if self.state.cond_nrnwz.locked():
                self.state.cond_nrnwz.notify()

    def __init__(self, *, loop=None):
        state = self._State(loop=loop)
        self.read_lock = self.ReadLock(state)
        self.write_lock = self.WriteLock(state)
