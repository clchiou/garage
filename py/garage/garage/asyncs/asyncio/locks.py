"""Synchronization primitives."""

__all__ = [
    'ReadWriteLock',
]

from asyncio.locks import (
    _ContextManagerMixin,
    Event,
)


class ReadWriteLock:

    class _State:

        def __init__(self, *, loop=None):
            self.num_readers = 0
            self.num_writers = 0
            # Event: num_writers == 0.
            self.event_nwz = Event(loop=loop)
            # Event: num_readers == num_writers == 0.
            self.event_nrnwz = Event(loop=loop)

    class ReadLock(_ContextManagerMixin):

        def __init__(self, state):
            self.state = state

        def locked(self):
            return self.state.num_writers != 0

        async def acquire(self):
            while self.locked():
                await self.state.event_nwz.wait()
            self.state.event_nwz.clear()
            self.state.num_readers += 1
            return True

        def release(self):
            if self.state.num_readers == 0:
                raise RuntimeError('ReadLock is not acquired')
            assert self.state.num_writers == 0
            self.state.num_readers -= 1
            if self.state.num_readers == 0:
                self.state.event_nrnwz.set()

    class WriteLock(_ContextManagerMixin):

        def __init__(self, state):
            self.state = state

        def locked(self):
            return self.state.num_readers != 0 or self.state.num_writers != 0

        async def acquire(self):
            while self.locked():
                await self.state.event_nrnwz.wait()
            self.state.event_nrnwz.clear()
            self.state.num_writers += 1
            return True

        def release(self):
            if self.state.num_writers == 0:
                raise RuntimeError('WriteLock is not acquired')
            assert self.state.num_readers == 0
            assert self.state.num_writers == 1
            self.state.num_writers = 0
            self.state.event_nwz.set()
            self.state.event_nrnwz.set()

    def __init__(self, *, loop=None):
        state = self._State(loop=loop)
        self.read_lock = self.ReadLock(state)
        self.write_lock = self.WriteLock(state)
