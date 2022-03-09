"""Helpers and fixes to stdlib's multiprocessing."""

__all__ = [
    'setup_forkserver_signal_handlers',
    'setup_pool_worker_signal_handlers',
]

import multiprocessing.forkserver
import signal


def setup_forkserver_signal_handlers():
    """Make forkserver ignore SIGTERM.

    You should call this once globally if you are using a forkserver.

    forkserver ignores SIGINT already; this makes it ignore SIGTERM as
    well.
    """
    mods = list(multiprocessing.forkserver._forkserver._preload_modules)
    mods.append(__package__ + '._multiprocessings_forkserver_init')
    multiprocessing.forkserver.set_forkserver_preload(mods)


def setup_pool_worker_signal_handlers():
    """Ignore SIGINT and SIGTERM.

    You should supply this to Pool's initializer argument.

    If a worker process aborts due to a signal (most commonly SIGINT and
    SIGTERM), Pool.terminate gets stuck.

    NOTE:
    * When Ctrl-C is pressed, SIGINT is sent to all processes.
    * The systemd's default KillMode "control-group" sends SIGTERM to
      all processes.
    """
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
