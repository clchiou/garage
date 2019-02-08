"""Start up ``supervise_servers``.

This ``parts`` module is unlike others in that it initializes the global
``supervise_servers``, not just provide "part maker" for it.
"""

from startup import startup

from g1.apps import labels
from g1.apps import parameters
from g1.apps import utils
from g1.asyncs import kernels
from g1.asyncs import servers

LABELS = labels.make_labels(
    servers.__name__,
    'supervise_servers',
    'server_queue',
    'graceful_exit',
    'grace_period',
    'serve',
)

PARAMS = parameters.define(
    servers.__name__,
    parameters.Namespace(
        grace_period=parameters.Parameter(4, unit='seconds'),
    ),
)

startup.set(LABELS.server_queue, kernels.TaskCompletionQueue())

startup.set(LABELS.graceful_exit, kernels.Event())

utils.depend_parameter_for(LABELS.grace_period, PARAMS.grace_period)

utils.define_binder(
    servers.supervise_servers,
    LABELS.supervise_servers,
    {
        'server_queue': LABELS.server_queue,
        'graceful_exit': LABELS.graceful_exit,
        'grace_period': LABELS.grace_period,
    },
)


@startup
def start_servers(server_queue: LABELS.server_queue, serves: [LABELS.serve]):
    for serve in serves:
        if serve:
            server_queue.spawn(serve)
