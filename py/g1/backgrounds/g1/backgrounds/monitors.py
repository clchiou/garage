import logging

from g1.apps import parameters
from g1.apps import utils
from g1.asyncs import kernels
from g1.asyncs.bases import timers
from g1.bases import labels

from . import executors
from . import tasks

LOG = logging.getLogger(__name__)

PARAMS = parameters.define(
    __name__,
    parameters.Namespace(
        'configure monitor',
        period=parameters.Parameter(
            10,
            type=(int, float),
            unit='seconds',
        ),
        executor_queue_threshold=parameters.Parameter(
            50,
            validate=(0).__le__,
        ),
        num_tasks_threshold=parameters.Parameter(
            200,
            validate=(0).__le__,
        ),
    ),
)

PARAMS_LABEL = labels.Label(__name__, 'params')


async def monitor(
    period,
    executor_queue_threshold,
    num_tasks_threshold,
    executor_queue,
):
    while True:
        queue_length = len(executor_queue)
        stats = kernels.get_kernel().get_stats()
        if (
            queue_length >= executor_queue_threshold
            or stats.num_tasks >= num_tasks_threshold
        ):
            LOG.info(
                'executor_queue_length=%d kernel_stats=%r',
                queue_length,
                stats,
            )
        await timers.sleep(period)


def define_monitor():
    utils.depend_parameter_for(PARAMS_LABEL, PARAMS)
    utils.define_maker(make_monitor)


def make_monitor(
    executor: executors.LABELS.executor,
    queue: tasks.LABELS.queue,
    params: PARAMS_LABEL,
):
    period = params.period.get()
    if period > 0:
        queue.spawn(
            monitor(
                period,
                params.executor_queue_threshold.get(),
                params.num_tasks_threshold.get(),
                executor.queue,
            )
        )
