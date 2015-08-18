"""Initialize logging."""

__all__ = [
    'init',
]

from startup import startup

from garage.functools import run_once

import garage.startups


@run_once
def init():
    startup(garage.startups.add_arguments)
    startup(garage.startups.configure)
