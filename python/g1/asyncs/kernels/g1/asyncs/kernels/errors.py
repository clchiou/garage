__all__ = [
    'Cancelled',
    'KernelTimeout',
    'TaskCancellation',
    'Timeout',
]


class TaskCancellation(BaseException):
    """Raise in a task on cancellation.

    This is similar to ``SystemExit`` and is raised **inside** the task
    that gets cancelled; thus it is inherited from ``BaseException``
    rather than ``Exception``.
    """


class Cancelled(Exception):
    """Raise when a task is cancelled.

    This is raised at the task that is waiting for a cancelled task, not
    the task that gets cancelled; thus it is a normal exception and is
    inherited from ``Exception``.
    """


class KernelTimeout(Exception):
    pass


class Timeout(Exception):
    pass
