__all__ = [
    'fail',
    'precond',
    'postcond',
]


def fail(message=None, *message_args):
    _fail(message, message_args)


def precond(cond, message=None, *message_args):
    _check(cond, message, message_args)


def postcond(cond, message=None, *message_args):
    _check(cond, message, message_args)


def _check(cond, message, message_args):
    if not cond:
        _fail(message, message_args)


def _fail(message, message_args):
    if message is None:
        raise AssertionError
    else:
        raise AssertionError(message % message_args)
