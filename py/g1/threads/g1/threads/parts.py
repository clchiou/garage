from g1.apps import bases
from g1.apps import parameters
from g1.apps import utils
from g1.bases import labels
from g1.bases.assertions import ASSERT

from . import executors
from . import queues

EXECUTOR_LABEL_NAMES = (
    # Output.
    'executor',
    # Private.
    'executor_params',
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
    capacity=0,
    name_prefix='',
    daemon=None,
    default_priority=None,
    parse_priority=None,
):
    # default_priority, when provided, is usually a domain object; so
    # caller should also provide a parse function.
    ASSERT.not_xor(default_priority is None, parse_priority is None)
    return parameters.Namespace(
        'make executor',
        max_executors=parameters.Parameter(max_executors, type=int),
        capacity=parameters.Parameter(capacity, type=int),
        name_prefix=parameters.Parameter(name_prefix, type=str),
        daemon=parameters.Parameter(daemon, type=(bool, type(None))),
        default_priority=(
            parameters.ConstParameter(None) if default_priority is None else \
            parameters.Parameter(
                default_priority, convert=parse_priority, format=str
            )
        ),
    )


def make_executor(
    exit_stack: bases.LABELS.exit_stack,
    params,
):
    if params.capacity.get() > 0:
        queue = queues.Queue(capacity=params.capacity.get())
    else:
        queue = None
    if params.default_priority.get() is None:
        executor_type = executors.Executor
        kwargs = {}
    else:
        executor_type = executors.PriorityExecutor
        kwargs = {'default_priority': params.default_priority.get()}
    return exit_stack.enter_context(
        executor_type(
            max_executors=params.max_executors.get(),
            queue=queue,
            name_prefix=params.name_prefix.get(),
            daemon=params.daemon.get(),
            **kwargs,
        ),
    )
