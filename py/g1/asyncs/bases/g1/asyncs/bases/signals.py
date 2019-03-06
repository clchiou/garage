__all__ = [
    'SignalSource',
]

import signal
import socket
import threading

from g1.bases.assertions import ASSERT
from g1.bases.classes import SingletonMeta

from . import adapters


class SignalSource(metaclass=SingletonMeta):
    """Signal queue.

    Python runtime implements a UNIX signal handler that writes signal
    number to a file descriptor (which is globally unique, by the way).
    ``SignalSource`` wraps this feature.

    NOTE: This class is a singleton (calling ``SignalSource()`` returns
    the same instance).  We make this design choice because UNIX signal
    handling is always strange and global.
    """

    def __init__(self):
        self._sock_r = self._sock_w = self._wakeup_fd = None
        self._handlers = {}

    def __enter__(self):
        # ``set_wakeup_fd`` can only be called from the main thread.
        ASSERT.is_(threading.current_thread(), threading.main_thread())
        # Disallow nested use; ``SignalSource`` is a singleton and is
        # intended to be used as such.
        ASSERT.none(self._wakeup_fd)
        sock_r, self._sock_w = socket.socketpair()
        self._sock_r = adapters.SocketAdapter(sock_r)
        self._sock_w.setblocking(False)
        self._wakeup_fd = signal.set_wakeup_fd(self._sock_w.fileno())
        return self

    def __exit__(self, *_):
        for signum in tuple(self._handlers):
            self.disable(signum)
        signal.set_wakeup_fd(self._wakeup_fd)
        self._sock_r.close()
        self._sock_w.close()
        self._sock_r = self._sock_w = self._wakeup_fd = None
        self._handlers.clear()

    def enable(self, signum):
        """Enable receiving signal ``signum``."""
        ASSERT.not_none(self._wakeup_fd)
        # Disallow repeated enable; ``SignalSource`` is a singleton and
        # is intended to be used as such.
        ASSERT.not_in(signum, self._handlers)
        # Register a dummy signal handler to ask Python to write the
        # signal number to the wakeup file descriptor.
        self._handlers[signum] = signal.signal(signum, _noop)
        # Set SA_RESTART to limit EINTR occurrences.
        signal.siginterrupt(signum, False)

    def disable(self, signum):
        """Disable receiving signal ``signum``."""
        ASSERT.not_none(self._wakeup_fd)
        ASSERT.in_(signum, self._handlers)
        signal.signal(signum, self._handlers.pop(signum))
        # Should we also restore ``signal.siginterrupt``?  But how?

    async def get(self):
        one_byte = (await self._sock_r.recv(1))[0]
        return signal.Signals(one_byte)  # pylint: disable=no-member


def _noop(*_):
    pass
