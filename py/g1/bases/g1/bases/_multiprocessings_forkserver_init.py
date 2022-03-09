"""Private module only for setting up forkserver's signal handlers."""

import signal

signal.signal(signal.SIGTERM, signal.SIG_IGN)
