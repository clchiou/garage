import logging

logging.getLogger(__name__).addHandler(logging.NullHandler())

BASE = 'base'
BUILDER_BASE = 'builder-base'


def is_debug():
    return logging.getLogger().isEnabledFor(logging.DEBUG)
