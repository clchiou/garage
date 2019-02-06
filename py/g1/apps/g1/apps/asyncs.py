"""Runner for asynchronous applications.

* Kernel context is created before ``exit_stack`` so that kernel is
  still accessible when ``exit_stack`` is cleaning up resources.

* There is no ``async_exit_stack`` because ``startup`` does not support
  asynchronous code at the moment.
"""

__all__ = [
    'LABELS',
    'run',
]

from g1.asyncs import kernels

from . import bases

# Re-export stuff.
from .bases import LABELS

run = kernels.with_kernel(bases.run)
