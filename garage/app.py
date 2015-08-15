"""Common application setup."""

__all__ = [
    'ARGS',
    'ARGV',
    'CONFIGURED',
    'PARSE',
    'PARSER',
    'init',
    'make_http_client',
]

import logging

from startup import startup

from garage.collections import FixedNamespace


#
# PARSER ---> PARSE --+--> ARGS ---> CONFIGURED
#                     |
#             ARGV ---+
#
ARGS = 'args'
ARGV = 'argv'
CONFIGURED = 'configured'
PARSE = 'parse'
PARSER = 'parser'


# app module's private variable.
_FEATURES = __name__ + '#features'


_CONFIGS = FixedNamespace(
    HTTP_USER_AGENT=None,
    HTTP_MAX_REQUESTS=0,
    HTTP_RETRY=0,
)


_LOG_FORMAT = '%(asctime)s %(levelname)s %(name)s: %(message)s'


_HTTP_USER_AGENT = (
    'Mozilla/5.0 (X11; Linux x86_64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/40.0.2214.111 Safari/537.36'
)


def make_http_client(configs=_CONFIGS):
    from garage.http import clients
    from garage.http import policies

    if configs.HTTP_USER_AGENT:
        user_agent = configs.HTTP_USER_AGENT
    else:
        user_agent = _HTTP_USER_AGENT

    if configs.HTTP_MAX_REQUESTS > 0:
        rate_limit = policies.MaxConcurrentRequests(configs.HTTP_MAX_REQUESTS)
    else:
        rate_limit = policies.Unlimited()

    if configs.HTTP_RETRY > 0:
        retry_policy = policies.BinaryExponentialBackoff(configs.HTTP_RETRY)
    else:
        retry_policy = policies.NoRetry()

    client = clients.Client(
        rate_limit=rate_limit,
        retry_policy=retry_policy,
    )
    client.headers['User-Agent'] = user_agent
    return client


def add_arguments(parser: PARSER, features: _FEATURES) -> PARSE:
    if all(not getattr(features, name) for name in dir(features)):
        return

    group = parser.add_argument_group(__name__)

    if features.use_logging:
        group.add_argument(
            '-v', '--verbose', action='count', default=0,
            help='verbose output')

    if features.use_http:
        group.add_argument(
            '--http-user-agent',
            help="""set http user agent""")
        group.add_argument(
            '--http-max-requests',
            type=int, default=_CONFIGS.HTTP_MAX_REQUESTS,
            help="""set max concurrent http requests or 0 for unlimited
                    (default %(default)s)
                 """)
        group.add_argument(
            '--http-retry',
            type=int, default=_CONFIGS.HTTP_RETRY,
            help="""set number of http retries or 0 for no retries
                    (default %(default)s)
                 """)


def parse_argv(parser: PARSER, argv: ARGV, _: PARSE) -> ARGS:
    return parser.parse_args(argv[1:])


def configure(args: ARGS, features: _FEATURES) -> CONFIGURED:
    if features.use_logging:
        if args.verbose == 0:
            level = logging.WARNING
        elif args.verbose == 1:
            level = logging.INFO
        else:
            level = logging.DEBUG
        logging.basicConfig(level=level, format=_LOG_FORMAT)

    if features.use_http:
        _CONFIGS.HTTP_USER_AGENT = args.http_user_agent
        _CONFIGS.HTTP_MAX_REQUESTS = args.http_max_requests
        _CONFIGS.HTTP_RETRY = args.http_retry


def init(*,
         use_logging=False,
         use_http=False):
    features = FixedNamespace(
        use_logging=use_logging,
        use_http=use_http,
    )
    if all(not getattr(features, name) for name in dir(features)):
        return
    startup.set(_FEATURES, features)
    startup(add_arguments)
    startup(parse_argv)
    startup(configure)
