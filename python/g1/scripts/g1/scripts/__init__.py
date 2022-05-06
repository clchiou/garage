"""Library for writing "shell script" style programs."""

import logging

from . import bases
from . import commands
from . import utils
# Re-export all.
from .bases import *
from .commands import *
from .utils import *

logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = bases.__all__ + commands.__all__ + utils.__all__
