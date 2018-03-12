import functools

from garage import parameters
from garage import parts
from garage.threads import executors


PARTS = parts.Parts(executors.__name__)
PARTS.worker_pool = parts.AUTO
PARTS.make_executor = parts.AUTO


PARAMS = parameters.define_namespace(
    executors.__name__, 'executor backed by global thread pool')
PARAMS.num_workers = parameters.create(
    8, 'set number of worker threads per executor')


@parts.define_maker
def make() -> (PARTS.worker_pool, PARTS.make_executor):
    worker_pool = executors.WorkerPool()
    make_executor = functools.partial(
        worker_pool.make_executor,
        PARAMS.num_workers.get(),
    )
    return worker_pool, make_executor
