from g1.apps import parameters
from g1.apps import utils
from g1.bases import labels
from g1.bases.assertions import ASSERT

from . import clients
from . import policies

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
    module_path = module_path or __package__
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


def make_session_params(
    user_agent='Mozilla/5.0',
    # Cache.
    cache_size=8,
    # Rate limit.
    max_request_rate=0,
    max_requests=0,
    # Retry.
    max_retries=0,
    backoff_base=1,
):
    return parameters.Namespace(
        'make HTTP client session',
        user_agent=parameters.Parameter(user_agent, type=str),
        cache_size=parameters.Parameter(cache_size, type=int),
        max_request_rate=parameters.Parameter(
            max_request_rate,
            type=(int, float),
            unit='requests/second',
        ),
        max_requests=parameters.Parameter(max_requests, type=int),
        max_retries=parameters.Parameter(max_retries, type=int),
        backoff_base=parameters.Parameter(
            backoff_base,
            type=(int, float),
            unit='seconds',
        ),
    )


def make_session(params, executor):
    session = clients.Session(
        executor=executor,
        cache_size=ASSERT.greater(params.cache_size.get(), 0),
        rate_limit=_make_rate_limit(params),
        retry=_make_retry(params),
    )
    user_agent = params.user_agent.get()
    if user_agent:
        session.headers['User-Agent'] = user_agent
    return session


def _make_rate_limit(params):
    max_request_rate = params.max_request_rate.get()
    if max_request_rate <= 0:
        return None
    return policies.TokenBucket(
        max_request_rate,
        ASSERT.greater(params.max_requests.get(), 0),
    )


def _make_retry(params):
    max_retries = params.max_retries.get()
    if max_retries <= 0:
        return None
    return policies.ExponentialBackoff(
        max_retries,
        ASSERT.greater(params.backoff_base.get(), 0),
    )
