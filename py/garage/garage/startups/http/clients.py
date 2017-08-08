"""Initialize garage.http.clients."""

__all__ = [
    'HttpClientComponent',
]

from garage import components
from garage.http import clients
from garage.http import policies


class HttpClientComponent(components.Component):

    HTTP_USER_AGENT = 'Mozilla/5.0'

    require = components.ARGS

    provide = components.make_fqname_tuple(__name__, 'http_client')

    def add_arguments(self, parser):
        group = parser.add_argument_group(clients.__name__)
        group.add_argument(
            '--http-user-agent', default=self.HTTP_USER_AGENT,
            help="""set http user agent (default to %(default)r)""")
        group.add_argument(
            '--http-max-requests', type=int, default=0,
            help="""set max concurrent http requests or 0 for unlimited
                    (default to %(default)s)
                 """)
        group.add_argument(
            '--http-retry', type=int, default=0,
            help="""set number of http retries or 0 for no retries
                    (default to %(default)s)
                 """)

    def make(self, require):
        args = require.args

        if args.http_max_requests > 0:
            rate_limit = policies.MaxConcurrentRequests(args.http_max_requests)
        else:
            rate_limit = policies.Unlimited()

        if args.http_retry > 0:
            retry_policy = policies.BinaryExponentialBackoff(args.http_retry)
        else:
            retry_policy = policies.NoRetry()

        http_client = clients.Client(
            rate_limit=rate_limit,
            retry_policy=retry_policy,
        )
        http_client.headers['User-Agent'] = args.http_user_agent

        return http_client
