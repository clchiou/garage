__all__ = [
    'SignalQueue',
    'uninstall_handlers',
]

import contextlib
import errno
import logging
import os
import signal
import struct
import threading

from garage import asserts
from garage.collections import SingletonMeta

from . import queues
from . import utils


LOG = logging.getLogger(__name__)


@contextlib.contextmanager
def uninstall_handlers(*signums):
    """Context for uninstalling default signal handlers."""
    with contextlib.ExitStack() as stack:
        for signum in signums:
            handler = signal.signal(signum, null_handler)
            stack.callback(signal.signal, signum, handler)
        yield


# You can't install SIG_IGN - that will even disable signal delivery to
# the wakeup fd.  Instead, you need a null handler.
def null_handler(signum, frame):
    pass


class SignalQueue(metaclass=SingletonMeta):

    THREAD_NAME = 'signals'

    CAPACITY = 64

    def __init__(self, capacity=None):

        current_thread = threading.current_thread()
        asserts.precond(
            current_thread.ident == threading.main_thread().ident,
            'expect signal queue be initialized in the main thread, not %r',
            current_thread,
        )

        if capacity is None:
            capacity = self.CAPACITY

        stack = contextlib.ExitStack()
        try:

            self._queue = queues.Queue(capacity=capacity)
            stack.callback(self._queue.close)

            rfd, wfd = os.pipe2(os.O_CLOEXEC)
            stack.callback(os.close, rfd)
            stack.callback(os.close, wfd)

            os.set_blocking(wfd, False)

            last_fd = signal.set_wakeup_fd(wfd)
            stack.callback(restore_wakeup_fd, last_fd, wfd)

            asserts.postcond(
                last_fd == -1,
                'expect no signal wakeup fd being set: %d', last_fd,
            )

            thread = threading.Thread(
                target=receive_signals,
                name=self.THREAD_NAME,
                args=(rfd, self._queue),
                daemon=True,
            )
            thread.start()
            utils.set_pthread_name(thread, self.THREAD_NAME)

        except Exception:
            stack.close()
            raise

        self._stack = stack

    def __bool__(self):
        return bool(self._queue)

    def __len__(self):
        return len(self._queue)

    def is_full(self):
        return self._queue.is_full()

    def is_closed(self):
        return self._queue.is_closed()

    def close(self, graceful=True):
        items = self._queue.close(graceful=graceful)
        self._stack.close()
        return items

    def get(self, block=True, timeout=None):
        return self._queue.get(block=block, timeout=timeout)


def restore_wakeup_fd(restore_fd, expect_fd):

    if threading.get_ident() != threading.main_thread().ident:
        LOG.error(
            'cannot restore signal wakeup fd in non-main thread: fd=%d',
            restore_fd,
        )
        return

    last_fd = signal.set_wakeup_fd(restore_fd)
    if last_fd != expect_fd:
        LOG.error(
            'expect last signal wakeup fd to be %d, not %d',
            expect_fd, last_fd,
        )


def receive_signals(rfd, queue):

    LOG.info('start receiving signals')
    try:

        while not queue.is_closed():

            try:
                data = os.read(rfd, 64)
            except OSError as e:
                if e.errno != errno.EBADF:
                    LOG.exception('cannot read signals: fd=%d', rfd)
                break

            signums = struct.unpack('%uB' % len(data), data)
            for signum in signums:

                try:
                    signum = signal.Signals(signum)
                except ValueError:
                    LOG.error('unrecognizable signum: %d', signum)

                try:
                    queue.put(signum, block=False)
                except queues.Full:
                    LOG.error('drop signal: %s', signum)
                except queues.Closed:
                    LOG.warning('drop signal and all the rest: %s', signum)
                    break

    except Exception:
        LOG.exception('encounter unexpected error')

    finally:
        # To notify the other side that I am dead.
        queue.close()

    LOG.info('exit')
