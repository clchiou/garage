__all__ = [
    'MAKE_EXECUTOR',
    'WORKER_POOL',
    'init',
]

import functools

from startup import startup

from garage.functools import run_once
from garage.threads import executors

from garage.startups import ARGS, PARSE, PARSER
from garage.startups import components


WORKER_POOL = __name__ + ':worker_pool'
MAKE_EXECUTOR = __name__ + ':make_executor'


MAX_WORKERS = 8


def add_arguments(parser: PARSER) -> PARSE:
    group = parser.add_argument_group(executors.__name__)
    group.add_argument(
        '--executor-workers', default=MAX_WORKERS,
        help="""set number of workers per executor
                (default to %(default)s)
             """)


def make_worker_pool() -> WORKER_POOL:
    return executors.WorkerPool()


def make_make_executor(worker_pool: WORKER_POOL, args: ARGS) -> MAKE_EXECUTOR:
    return functools.partial(worker_pool.make_executor, args.executor_workers)


@run_once
def init():
    startup(add_arguments)
    components.startup(make_worker_pool)
    components.startup(make_make_executor)
