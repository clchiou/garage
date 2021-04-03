"""Blocking traps.

When a task requests a kernel service, such as I/O or spawning a new
task, it issues a trap.  Traps are either blocking or non-blocking.
When a task issues a blocking trap, it will yield, but when issuing a
non-blocking trap, it will resume execution after kernel returns.
"""

__all__ = [
    'Traps',
    'block',
    'join',
    'poll_read',
    'poll_write',
    'sleep',
]

import collections
import enum
import types

from . import pollers


class Traps(enum.Enum):
    """Enumerate blocking traps."""
    BLOCK = enum.auto()
    JOIN = enum.auto()
    POLL = enum.auto()
    SLEEP = enum.auto()


BlockTrap = collections.namedtuple(
    'BlockTrap', 'kind source post_block_callback'
)
JoinTrap = collections.namedtuple('JoinTrap', 'kind task')
PollTrap = collections.namedtuple('PollTrap', 'kind fd events')
SleepTrap = collections.namedtuple('SleepTrap', 'kind duration')


@types.coroutine
def block(source, post_block_callback=None):
    yield BlockTrap(Traps.BLOCK, source, post_block_callback)


@types.coroutine
def join(task):
    yield JoinTrap(Traps.JOIN, task)


@types.coroutine
def poll_read(fd):
    yield PollTrap(Traps.POLL, fd, pollers.Polls.READ)


@types.coroutine
def poll_write(fd):
    yield PollTrap(Traps.POLL, fd, pollers.Polls.WRITE)


@types.coroutine
def sleep(duration):
    yield SleepTrap(Traps.SLEEP, duration)
