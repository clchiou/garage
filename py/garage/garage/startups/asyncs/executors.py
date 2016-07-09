__all__ = [
    'ExecutorComponent',
]

import functools

from garage import components
from garage.asyncs import executors
from garage.asyncs.executors import WorkerPoolAdapter
from garage.threads.executors import WorkerPool

from . import LOOP


class ExecutorComponent(components.Component):

    MAX_WORKERS = 8

    require = (
        components.ARGS,
        components.EXIT_STACK,
        LOOP,
    )

    provide = components.make_fqname_tuple(
        __name__,
        'worker_pool',
        'make_executor',
    )

    def add_arguments(self, parser):
        group = parser.add_argument_group(executors.__name__)
        group.add_argument(
            '--async-executor-workers',
            type=int, default=self.MAX_WORKERS,
            help="""set number of workers per async executor
                    (default to %(default)s)
                 """)

    def make(self, require):
        worker_pool = WorkerPoolAdapter(WorkerPool(), loop=require.loop)
        require.exit_stack.callback(worker_pool.shutdown)
        return (
            worker_pool,
            functools.partial(
                worker_pool.make_executor,
                require.args.async_executor_workers,
            )
        )
