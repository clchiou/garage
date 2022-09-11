__all__ = [
    'DEFAULT_HEADERS',
    'make_connection_pool_params_dict',
    'make_params_dict',
    'make_rate_limit',
    'make_retry',
]

from g1.apps import parameters

from .. import policies

DEFAULT_HEADERS = {'User-Agent': 'Mozilla/5.0'}


def make_params_dict(
    # Cache.
    cache_size=8,
    # Circuit breaker.
    failure_threshold=0,
    failure_period=8,
    failure_timeout=8,
    success_threshold=2,
    # Rate limit.
    max_request_rate=0,
    max_requests=64,
    raise_unavailable=False,
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
        failure_threshold=parameters.Parameter(
            failure_threshold,
            type=int,
            validate=(0).__le__,
        ),
        failure_period=parameters.Parameter(
            failure_period,
            type=(int, float),
            validate=(0).__lt__,
            unit='seconds',
        ),
        failure_timeout=parameters.Parameter(
            failure_timeout,
            type=(int, float),
            validate=(0).__lt__,
            unit='seconds',
        ),
        success_threshold=parameters.Parameter(
            success_threshold,
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
        raise_unavailable=parameters.Parameter(
            raise_unavailable,
            type=bool,
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


def make_circuit_breakers(params):
    failure_threshold = params.failure_threshold.get()
    if failure_threshold <= 0:
        return None
    return policies.TristateBreakers(
        failure_threshold=failure_threshold,
        failure_period=params.failure_period.get(),
        failure_timeout=params.failure_timeout.get(),
        success_threshold=params.success_threshold.get(),
    )


def make_rate_limit(params):
    max_request_rate = params.max_request_rate.get()
    if max_request_rate <= 0:
        return None
    return policies.TokenBucket(
        max_request_rate,
        params.max_requests.get(),
        params.raise_unavailable.get(),
    )


def make_retry(params):
    max_retries = params.max_retries.get()
    if max_retries <= 0:
        return None
    return policies.ExponentialBackoff(max_retries, params.backoff_base.get())
