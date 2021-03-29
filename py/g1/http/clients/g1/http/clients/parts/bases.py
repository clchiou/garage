__all__ = [
    'DEFAULT_USER_AGENT',
    'make_connection_pool_params_dict',
    'make_params_dict',
    'make_rate_limit',
    'make_retry',
]

from g1.apps import parameters

from .. import policies

DEFAULT_USER_AGENT = 'Mozilla/5.0'


def make_params_dict(
    # Cache.
    cache_size=8,
    # Rate limit.
    max_request_rate=0,
    max_requests=64,
    # Retry.
    max_retries=0,
    backoff_base=1,
):
    return dict(
        cache_size=parameters.Parameter(
            cache_size,
            type=int,
            validate=(0).__lt__,
        ),
        max_request_rate=parameters.Parameter(
            max_request_rate,
            type=(int, float),
            unit='requests/second',
        ),
        max_requests=parameters.Parameter(
            max_requests,
            type=int,
            validate=(0).__lt__,
        ),
        max_retries=parameters.Parameter(max_retries, type=int),
        backoff_base=parameters.Parameter(
            backoff_base,
            type=(int, float),
            validate=(0).__lt__,
            unit='seconds',
        ),
    )


def make_connection_pool_params_dict(
    num_pools=0,
    num_connections_per_pool=0,
):
    return dict(
        num_pools=parameters.Parameter(
            num_pools,
            type=int,
            validate=(0).__le__,
        ),
        num_connections_per_pool=parameters.Parameter(
            num_connections_per_pool,
            type=int,
            validate=(0).__le__,
        ),
    )


def make_rate_limit(params):
    max_request_rate = params.max_request_rate.get()
    if max_request_rate <= 0:
        return None
    return policies.TokenBucket(max_request_rate, params.max_requests.get())


def make_retry(params):
    max_retries = params.max_retries.get()
    if max_retries <= 0:
        return None
    return policies.ExponentialBackoff(max_retries, params.backoff_base.get())
