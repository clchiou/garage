"""Define a global multiprocessing.Pool."""

import multiprocessing

from g1.apps import bases
from g1.apps import parameters
from g1.apps import utils
from g1.bases import labels

LABELS = labels.make_labels(
    __name__,
    # Output.
    'pool',
    # Private.
    'pool_params',
)

PARAMS = parameters.define(
    __name__,
    parameters.Namespace(
        # Even with forkserver, a process worker still has a pretty big
        # memory footprint; so we cannot launch too many of them.
        pool_size=parameters.Parameter(4),
        max_uses_per_worker=parameters.Parameter(64),
    ),
)

utils.depend_parameter_for(LABELS.pool_params, PARAMS)


@utils.define_maker
def make_pool(
    params: LABELS.pool_params,
    exit_stack: bases.LABELS.exit_stack,
) -> LABELS.pool:
    # Based on our experiments, "forkserver" seems to use less memory
    # than the default "fork".  The reason appears to be that "fork"
    # forks from the main process, which usually has a bigger memory
    # footprint than the fork server.
    return exit_stack.enter_context(
        multiprocessing.get_context('forkserver').Pool(
            processes=params.pool_size.get(),
            maxtasksperchild=params.max_uses_per_worker.get(),
        )
    )
