from g1.apps import bases
from g1.apps import parameters
from g1.apps import utils
from g1.bases import labels

from . import executors

EXECUTOR_LABEL_NAMES = (
    'executor_params',
    'executor',
)


def define_executor(module_path=None, **kwargs):
    """Define an executor under ``module_path``."""
    module_path = module_path or executors.__name__
    module_labels = labels.make_labels(module_path, *EXECUTOR_LABEL_NAMES)
    setup_executor(
        module_labels,
        parameters.define(module_path, make_executor_params(**kwargs)),
    )
    return module_labels


def setup_executor(module_labels, module_params):
    utils.depend_parameter_for(module_labels.executor_params, module_params)
    utils.define_maker(
        make_executor,
        {
            'params': module_labels.executor_params,
            'return': module_labels.executor,
        },
    )


def make_executor_params(
    *,
    max_executors=0,
    name_prefix='',
    daemon=None,
    default_priority=None,
):
    return parameters.Namespace(
        'make executor',
        max_executors=parameters.Parameter(max_executors, type=int),
        name_prefix=parameters.Parameter(name_prefix, type=str),
        daemon=parameters.Parameter(daemon, type=(bool, type(None))),
        default_priority=parameters.Parameter(
            default_priority, type=object, format=str
        ),
    )


def make_executor(
    exit_stack: bases.LABELS.exit_stack,
    params,
):
    if params.default_priority.get() is None:
        executor_type = executors.Executor
        kwargs = {}
    else:
        executor_type = executors.PriorityExecutor
        kwargs = {'default_priority': params.default_priority.get()}
    return exit_stack.enter_context(
        executor_type(
            max_executors=params.max_executors.get(),
            name_prefix=params.name_prefix.get(),
            daemon=params.daemon.get(),
            **kwargs,
        ),
    )
