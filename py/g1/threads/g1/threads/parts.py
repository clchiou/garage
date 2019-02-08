from g1.apps import bases
from g1.apps import parameters
from g1.threads import executors


def make_executor_params(
    *,
    max_executors=0,
    name_prefix='',
    daemon=None,
):
    return parameters.Namespace(
        'make executor',
        max_executors=parameters.Parameter(max_executors),
        name_prefix=parameters.Parameter(name_prefix),
        daemon=parameters.Parameter(daemon, type=(bool, type(None))),
    )


def make_executor(
    exit_stack: bases.LABELS.exit_stack,
    params,
):
    return exit_stack.enter_context(
        executors.Executor(
            max_executors=params.max_executors.get(),
            name_prefix=params.name_prefix.get(),
            daemon=params.daemon.get(),
        ),
    )
