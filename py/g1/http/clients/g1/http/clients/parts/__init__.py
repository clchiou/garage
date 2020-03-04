from g1.apps import parameters
from g1.apps import utils
from g1.bases import labels

from ... import clients
from . import bases

SESSION_LABEL_NAMES = (
    # Input.
    'executor',
    # Output.
    'session',
    # Private.
    'session_params',
)


def define_session(module_path=None, **kwargs):
    """Define a session object under ``module_path``."""
    module_path = module_path or clients.__name__
    module_labels = labels.make_labels(module_path, *SESSION_LABEL_NAMES)
    setup_session(
        module_labels,
        parameters.define(
            module_path,
            make_session_params(**kwargs),
        ),
    )
    return module_labels


def setup_session(module_labels, module_params):
    utils.depend_parameter_for(module_labels.session_params, module_params)
    utils.define_maker(
        make_session,
        {
            'params': module_labels.session_params,
            'executor': module_labels.executor,
            'return': module_labels.session,
        },
    )


def make_session_params(user_agent=bases.DEFAULT_USER_AGENT, **kwargs):
    return parameters.Namespace(
        'make HTTP client session',
        user_agent=parameters.Parameter(user_agent, type=str),
        **bases.make_params_dict(**kwargs),
    )


def make_session(params, executor):
    session = clients.Session(
        executor=executor,
        cache_size=params.cache_size.get(),
        rate_limit=bases.make_rate_limit(params),
        retry=bases.make_retry(params),
    )
    user_agent = params.user_agent.get()
    if user_agent:
        session.headers['User-Agent'] = user_agent
    return session
