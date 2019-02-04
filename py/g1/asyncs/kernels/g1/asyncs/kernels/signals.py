__all__ = [
    'SignalQueue',
]

import signal
import socket
import struct
import threading

from g1.bases.assertions import ASSERT
from g1.bases.classes import SingletonMeta

from . import adapters


class SignalQueue(metaclass=SingletonMeta):
    """Signal queue.

    Python runtime implements a UNIX signal handler that writes signal
    number to a file descriptor (which is globally unique, by the way).
    ``SignalQueue`` wraps this feature with a queue-like interface.

    NOTE: This class is a singleton (calling ``SignalQueue()`` returns
    the same instance).  We make this design choice because UNIX signal
    handling is always strange and global.
    """

    def __init__(self):
        ASSERT.is_(threading.current_thread(), threading.main_thread())
        sock_r, self._sock_w = socket.socketpair()
        self._sock_r = adapters.SocketAdapter(sock_r)
        self._sock_w.setblocking(False)
        self._original_wakeup_fd = signal.set_wakeup_fd(self._sock_w.fileno())
        self._original_handlers = {}

    def subscribe(self, signum):
        """Subscribe to ``signum`` signal."""
        if signum in self._original_handlers:
            return
        # Register a dummy signal handler to ask Python to write the
        # signal number to the wakeup file descriptor.
        self._original_handlers[signum] = signal.signal(signum, _noop)
        # Set SA_RESTART to limit EINTR occurrences.
        signal.siginterrupt(signum, False)

    def unsubscribe(self, signum):
        if signum not in self._original_handlers:
            return
        signal.signal(signum, self._original_handlers.pop(signum))
        # Should we also restore ``signal.siginterrupt``?

    def close(self):
        for signum in tuple(self._original_handlers):
            self.unsubscribe(signum)
        signal.set_wakeup_fd(self._original_wakeup_fd)
        self._sock_r.target.close()
        self._sock_w.close()

    async def get(self):
        one_byte = await self._sock_r.recv(1)
        signum = struct.unpack('B', one_byte)[0]
        return signal.Signals(signum)  # pylint: disable=no-member


def _noop(*_):
    pass
