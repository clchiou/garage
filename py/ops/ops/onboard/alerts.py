__all__ = [
    'alerts',
]

from pathlib import Path
import json
import os
import urllib.request

from garage import apps
from garage import scripts
from garage.assertions import ASSERT


SLACK_COLOR_TABLE = {
    'info': '',
    'good': 'good',
    'warning': 'warning',
    'error': 'danger',
}


def _get(config, *fields):
    for field in fields:
        ASSERT.in_(field, config)
        config = config[field]
    return config


@apps.with_help('send alert')
@apps.with_argument(
    '--config', type=Path, default='/etc/ops/config.json',
    help='set config file path (default to %(default)s)'
)
@apps.with_argument(
    '--level', choices=('info', 'good', 'warning', 'error'),
    help='set alert level'
)
@apps.with_argument(
    '--hostname',
    help='set hostname'
)
@apps.with_argument(
    '--systemd-service-result',
    help='provide service result for deriving alert level'
)
@apps.with_argument(
    '--title', required=True,
    help='set title of alert message',
)
@apps.with_argument(
    '--description', required=True,
    help='set alert description',
)
def send(args):
    """Send alert."""

    config = json.loads(scripts.ensure_file(args.config).read_text())

    # For now, only one destination `slack` is supported; so it has to
    # be present.
    webhook = _get(config, 'alerts', 'destinations', 'slack', 'webhook')

    if args.level:
        level = args.level
    elif args.systemd_service_result:
        if args.systemd_service_result == 'success':
            level = 'good'
        else:
            level = 'error'
    else:
        level = 'info'

    hostname = args.hostname or os.uname().nodename

    message = {
        # Should we make these configurable?
        'username': 'ops-onboard',
        'icon_emoji': ':robot_face:',
        'attachments': [
            {
                'fallback': '%s: %s: %s' % (
                    hostname,
                    args.title,
                    args.description,
                ),
                'color': SLACK_COLOR_TABLE[level],
                'fields': [
                    {
                        'title': args.title,
                        'value': args.description,
                        'short': True,
                    },
                    {
                        'title': 'Host',
                        'value': hostname,
                        'short': True,
                    },
                ],
            },
        ],
    }

    # urlopen checks the HTTP status code for us.
    urllib.request.urlopen(urllib.request.Request(
        webhook,
        headers={'Content-Type': 'application/json'},
        data=json.dumps(message).encode('utf-8'),
    ))

    return 0


@apps.with_help('manage alerts')
@apps.with_defaults(no_locking_required=True)
@apps.with_apps(
    'operation', 'operation on alerts',
    send,
)
def alerts(args):
    """Manage alerts."""
    return args.operation(args)
