import logging

from g1.apps import parameters
from g1.apps import utils
from g1.asyncs import kernels
from g1.asyncs.bases import timers
from g1.bases import labels
from g1.bases import lifecycles

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
        num_tasks_threshold=parameters.Parameter(
            100,
            validate=(0).__le__,
        ),
    ),
)

PARAMS_LABEL = labels.Label(__name__, 'params')


async def monitor(period, num_tasks_threshold):
    while True:
        stats = kernels.get_kernel().get_stats()
        if stats.num_tasks >= num_tasks_threshold:
            LOG.info('kernel stats: %r', stats)
            LOG.info('lifecycle snapshot: %r', lifecycles.take_snapshot())
        await timers.sleep(period)


def define_monitor():
    utils.depend_parameter_for(PARAMS_LABEL, PARAMS)
    utils.define_maker(make_monitor)


def make_monitor(queue: tasks.LABELS.queue, params: PARAMS_LABEL):
    period = params.period.get()
    if period > 0:
        queue.spawn(monitor(period, params.num_tasks_threshold.get()))
