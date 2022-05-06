__all__ = [
    'Timeout',
    'sleep',
    'timeout_after',
    'timeout_ignore',
]

from g1.asyncs.kernels import contexts

# Re-export errors.
from g1.asyncs.kernels.errors import Timeout
# Re-export it without modifications, for now.
from g1.asyncs.kernels.traps import sleep


class timeout_after:

    def __init__(self, duration, *, task=None):
        kernel = contexts.get_kernel()
        if not task:
            task = kernel.get_current_task()
            if not task:
                raise LookupError('no current task: %r' % kernel)
        self._cancel = kernel.timeout_after(task, duration)

    def __call__(self):
        return self._cancel()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._cancel()


class timeout_ignore(timeout_after):

    def __exit__(self, exc_type, *_):
        self._cancel()
        return exc_type is not None and issubclass(exc_type, Timeout)
