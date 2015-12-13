import atexit
import logging
import os
from contextlib import ExitStack

if os.getenv('DEBUG'):
    logging.basicConfig(level=logging.INFO)

from v8 import V8


stack = ExitStack()
stack.__enter__()
atexit.register(stack.close)


v8 = stack.enter_context(V8())
