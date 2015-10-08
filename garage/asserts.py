__all__ = [
    'precond',
    'postcond',
]


def precond(cond, message=None, *message_args):
    _check(cond, message, message_args)


def postcond(cond, message=None, *message_args):
    _check(cond, message, message_args)


def _check(cond, message, message_args):
    if not cond:
        if message is None:
            raise AssertionError
        else:
            raise AssertionError(message % message_args)
