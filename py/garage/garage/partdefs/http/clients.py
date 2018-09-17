from garage import parameters
from garage import parts
from garage.assertions import ASSERT
from garage.http import clients
from garage.http import policies


def create_parts(module_name=None):
    part_list = parts.Parts(module_name)
    part_list.client = parts.AUTO
    return part_list


def create_params(
        *,
        user_agent='Mozilla/5.0',
        max_request_rate=0.0,
        max_requests=0.0,
        num_retries=0):
    params = parameters.create_namespace(
        'create http client')
    params.user_agent = parameters.create(
        user_agent,
        'set HTTP user agent',
    )
    params.max_request_rate = parameters.create(
        max_request_rate,
        'set max requests per second where 0 means unlimited',
    )
    params.max_requests = parameters.create(
        max_requests,
        'set token bucket size',
    )
    params.num_retries = parameters.create(
        num_retries,
        'set retries where 0 means no retry',
    )
    return params


def create_maker(part_list, params):

    def make_client() -> part_list.client:

        if params.max_request_rate.get() > 0:
            ASSERT.greater(params.max_requests.get(), 0)
            rate_limit = policies.TokenBucket(
                params.max_request_rate.get(),
                params.max_requests.get(),
            )
        else:
            rate_limit = policies.Unlimited()

        if params.num_retries.get() > 0:
            retry_policy = policies.BinaryExponentialBackoff(
                params.num_retries.get(),
            )
        else:
            retry_policy = policies.NoRetry()

        client = clients.Client(
            rate_limit=rate_limit,
            retry_policy=retry_policy,
        )
        client.headers['User-Agent'] = params.user_agent.get()

        return client

    return make_client


# The default HTTP client object.
PARTS = create_parts(clients.__name__)
PARAMS = parameters.define_namespace(
    clients.__name__,
    namespace=create_params(),
)
parts.define_maker(create_maker(PARTS, PARAMS))
