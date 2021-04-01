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
            600,
            type=(int, float),
            unit='seconds',
        ),
    ),
)

PARAMS_LABEL = labels.Label(__name__, 'params')


async def monitor(period):
    while True:
        LOG.info('kernel stats: %r', kernels.get_kernel().get_stats())
        LOG.info('lifecycle snapshot: %r', lifecycles.take_snapshot())
        await timers.sleep(period)


def define_monitor():
    utils.depend_parameter_for(PARAMS_LABEL, PARAMS)
    utils.define_maker(make_monitor)


def make_monitor(queue: tasks.LABELS.queue, params: PARAMS_LABEL):
    period = params.period.get()
    if period > 0:
        queue.spawn(monitor(period))
