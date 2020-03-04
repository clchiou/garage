from g1.apps import parameters
from g1.apps import utils

from .. import clusters
from . import bases

SESSION_LABEL_NAMES = (
    # Input.
    'stubs',
    'executor',
    # Output.
    'session',
    # Private.
    'session_params',
)

STUB_LABEL_NAMES = (
    # Output.
    'stub',
    # Private.
    'stub_params',
)


def setup_session(module_labels, module_params):
    utils.depend_parameter_for(module_labels.session_params, module_params)
    utils.define_maker(
        make_session,
        {
            'params': module_labels.session_params,
            'stubs': [module_labels.stubs],
            'executor': module_labels.executor,
            'return': module_labels.session,
        },
    )


def setup_stub(module_labels, module_params):
    utils.depend_parameter_for(module_labels.stub_params, module_params)
    utils.define_maker(
        make_stub,
        {
            'params': module_labels.stub_params,
            'return': module_labels.stub,
        },
    )


def make_session_params(user_agent=bases.DEFAULT_USER_AGENT):
    return parameters.Namespace(
        'make HTTP cluster session',
        user_agent=parameters.Parameter(user_agent, type=str),
    )


def make_stub_params(**kwargs):
    return parameters.Namespace(
        'make HTTP cluster stub',
        **bases.make_params_dict(**kwargs),
    )


def make_session(params, stubs, executor):
    session = clusters.ClusterSession(stubs, executor)
    user_agent = params.user_agent.get()
    if user_agent:
        session.headers['User-Agent'] = user_agent
    return session


def make_stub(params):
    return clusters.ClusterStub(
        cache_size=params.cache_size.get(),
        rate_limit=bases.make_rate_limit(params),
        retry=bases.make_retry(params),
    )
