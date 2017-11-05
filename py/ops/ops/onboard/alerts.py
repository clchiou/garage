__all__ = [
    'alerts',
]

from pathlib import Path
import json
import os
import urllib.request

from garage import asserts, cli, scripts
from garage.components import ARGS


SLACK_COLOR_TABLE = {
    'info': '',
    'good': 'good',
    'warning': 'warning',
    'error': 'danger',
}


def _get(config, *fields):
    for field in fields:
        asserts.in_(field, config)
        config = config[field]
    return config


@cli.command(help='send alert')
@cli.argument(
    '--config', type=Path, default='/etc/ops/config.json',
    help='set config file path (default to %(default)s)'
)
@cli.argument(
    '--level', choices=('info', 'good', 'warning', 'error'),
    help='set alert level'
)
@cli.argument(
    '--hostname',
    help='set hostname'
)
@cli.argument(
    '--systemd-service-result',
    help='provide service result for deriving alert level'
)
@cli.argument(
    '--title', required=True,
    help='set title of alert message',
)
@cli.argument(
    '--description', required=True,
    help='set alert description',
)
def send(args: ARGS):
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


@cli.command(help='manage alerts')
@cli.defaults(no_locking_required=True)
@cli.sub_command_info('operation', 'operation on alerts')
@cli.sub_command(send)
def alerts(args: ARGS):
    """Manage alerts."""
    return args.operation()
