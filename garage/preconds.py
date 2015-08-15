__all__ = [
    'check_argument',
    'check_state',
]


class IllegalArgumentException(Exception):
    pass


class IllegalStateException(Exception):
    pass


def check_argument(cond, message=None, *message_args):
    _check(cond, IllegalArgumentException, message, message_args)


def check_state(cond, message=None, *message_args):
    _check(cond, IllegalStateException, message, message_args)


def _check(cond, exc_class, message, message_args):
    if not cond:
        if message is None:
            raise exc_class
        else:
            raise exc_class(message % message_args)
