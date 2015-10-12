__all__ = [
    'ExecutorComponent',
]

import functools

from garage import components
from garage.threads import executors


class ExecutorComponent(components.Component):

    MAX_WORKERS = 8

    require = components.ARGS

    provide = components.make_provide(__name__, 'worker_pool', 'make_executor')

    def add_arguments(self, parser):
        group = parser.add_argument_group(executors.__name__)
        group.add_argument(
            '--executor-workers',
            default=self.MAX_WORKERS, type=int,
            help="""set number of workers per executor
                    (default to %(default)s)
                 """)

    def make(self, require):
        worker_pool = executors.WorkerPool()
        return (
            worker_pool,
            functools.partial(
                worker_pool.make_executor,
                require.args.executor_workers,
            )
        )
