from g1.apps import parameters
from g1.apps import utils
from g1.bases import labels

from ... import clients  # pylint: disable=relative-beyond-top-level
from .. import policies
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


def make_session_params(
    # pylint: disable=dangerous-default-value
    headers=bases.DEFAULT_HEADERS,
    block_all_cookies=True,
    num_pools=0,
    num_connections_per_pool=0,
    **kwargs,
):
    return parameters.Namespace(
        'make HTTP client session',
        headers=parameters.Parameter(headers, type=dict),
        block_all_cookies=parameters.Parameter(block_all_cookies, type=bool),
        **bases.make_params_dict(**kwargs),
        **bases.make_connection_pool_params_dict(
            num_pools=num_pools,
            num_connections_per_pool=num_connections_per_pool,
        ),
    )


def make_session(params, executor):
    session = clients.Session(
        executor=executor,
        cache_size=params.cache_size.get(),
        circuit_breakers=bases.make_circuit_breakers(params),
        rate_limit=bases.make_rate_limit(params),
        retry=bases.make_retry(params),
        num_pools=params.num_pools.get(),
        num_connections_per_pool=params.num_connections_per_pool.get(),
    )
    session.headers.update(params.headers.get())
    if params.block_all_cookies.get():
        session.cookies.set_policy(policies.BlockAllCookiePolicy())
    return session
