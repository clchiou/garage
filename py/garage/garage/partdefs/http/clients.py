from garage import parameters
from garage import parts
from garage.http import clients
from garage.http import policies


PARTS = parts.PartList(clients.__name__, [
    ('client', parts.AUTO),
])


PARAMS = parameters.get(
    clients.__name__, 'http client library')
PARAMS.user_agent = parameters.define(
    'Mozilla/5.0', 'set HTTP user agent')
PARAMS.max_requests = parameters.define(
    0, 'set max concurrent HTTP requests where 0 means unlimited')
PARAMS.num_retries = parameters.define(
    0, 'set retries where 0 means no retry')


@parts.register_maker
def make_client() -> PARTS.client:

    if PARAMS.max_requests.get() > 0:
        rate_limit = policies.MaxConcurrentRequests(
            PARAMS.max_requests.get())
    else:
        rate_limit = policies.Unlimited()

    if PARAMS.num_retries.get() > 0:
        retry_policy = policies.BinaryExponentialBackoff(
            PARAMS.num_retries.get())
    else:
        retry_policy = policies.NoRetry()

    client = clients.Client(
        rate_limit=rate_limit,
        retry_policy=retry_policy,
    )
    client.headers['User-Agent'] = PARAMS.user_agent.get()

    return client
