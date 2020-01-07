import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())


def is_debug():
    return logging.getLogger().isEnabledFor(logging.DEBUG)
