from g1.apps import labels
from g1.apps import parameters
from g1.apps import utils
from g1.bases.assertions import ASSERT
from g1.http import clients
from g1.http.clients import policies


def define_session(module_path=None, *, executor_label=None, **kwargs):
    """Define a session object under ``module_path``."""

    module_path = module_path or clients.__name__

    module_labels = labels.make_labels(
        module_path,
        'session_params',
        'session',
    )

    utils.depend_parameter_for(
        module_labels.session_params,
        parameters.define(
            module_path,
            make_session_params(**kwargs),
        ),
    )

    annotations = {
        'params': module_labels.session_params,
        'return': module_labels.session,
    }
    if executor_label:
        annotations['executor'] = executor_label
    utils.define_maker(make_session, annotations)

    return module_labels


def make_session_params(
    user_agent='Mozilla/5.0',
    # Rate limit.
    max_request_rate=0,
    max_requests=0,
    # Retry.
    max_retries=0,
    backoff_base=1,
):
    return parameters.Namespace(
        'make HTTP client session',
        user_agent=parameters.Parameter(user_agent),
        max_request_rate=parameters.Parameter(
            max_request_rate,
            type=(int, float),
            unit='requests/second',
        ),
        max_requests=parameters.Parameter(max_requests),
        max_retries=parameters.Parameter(max_retries),
        backoff_base=parameters.Parameter(
            backoff_base,
            type=(int, float),
            unit='seconds',
        ),
    )


def make_session(params, executor=None):

    max_request_rate = params.max_request_rate.get()
    if max_request_rate > 0:
        rate_limit = policies.TokenBucket(
            max_request_rate,
            ASSERT.greater(params.max_requests.get(), 0),
        )
    else:
        rate_limit = None

    max_retries = params.max_retries.get()
    if max_retries > 0:
        retry = policies.ExponentialBackoff(
            max_retries,
            ASSERT.greater(params.backoff_base.get(), 0),
        )
    else:
        retry = None

    session = clients.Session(
        executor=executor,
        rate_limit=rate_limit,
        retry=retry,
    )

    user_agent = params.user_agent.get()
    if user_agent:
        session.headers['User-Agent'] = user_agent

    return session
