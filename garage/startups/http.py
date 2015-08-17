"""Initialize http."""

__all__ = [
    'init',
    'make_client',
]

from startup import startup

from garage import startups
from garage.collections import FixedNamespace
from garage.http import clients
from garage.http import policies


HTTP_USER_AGENT = (
    'Mozilla/5.0 (X11; Linux x86_64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/40.0.2214.111 Safari/537.36'
)


CONFIGS = __name__ + '#configs'


def make_client(configs=None):
    configs = configs or make_client.configs

    if configs.http_max_requests > 0:
        rate_limit = policies.MaxConcurrentRequests(configs.http_max_requests)
    else:
        rate_limit = policies.Unlimited()

    if configs.http_retry > 0:
        retry_policy = policies.BinaryExponentialBackoff(configs.http_retry)
    else:
        retry_policy = policies.NoRetry()

    client = clients.Client(
        rate_limit=rate_limit,
        retry_policy=retry_policy,
    )
    client.headers['User-Agent'] = configs.http_user_agent

    return client


make_client.configs = FixedNamespace(
    http_user_agent=HTTP_USER_AGENT,
    http_max_requests=0,
    http_retry=0,
)


def add_arguments(parser: startups.PARSER, configs: CONFIGS) -> startups.PARSE:
    group = parser.add_argument_group(__name__)
    group.add_argument(
        '--http-user-agent',
        help="""set http user agent""")
    group.add_argument(
        '--http-max-requests',
        type=int, default=configs.http_max_requests,
        help="""set max concurrent http requests or 0 for unlimited
                (default to %(default)s)
             """)
    group.add_argument(
        '--http-retry',
        type=int, default=configs.http_retry,
        help="""set number of http retries or 0 for no retries
                (default to %(default)s)
             """)


def configure(args: startups.ARGS, configs: CONFIGS) -> startups.CONFIGURED:
    configs.http_user_agent = args.http_user_agent
    configs.http_max_requests = args.http_max_requests
    configs.http_retry = args.http_retry


def init():
    startup.set(CONFIGS, make_client.configs)
    startup(add_arguments)
    startup(configure)
