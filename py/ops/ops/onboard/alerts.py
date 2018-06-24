__all__ = [
    'alerts',
]

from pathlib import Path
import enum
import json
import os
import urllib.request

from garage import apps
from garage import scripts


class Levels(enum.Enum):
    INFO = enum.auto()
    GOOD = enum.auto()
    WARNING = enum.auto()
    ERROR = enum.auto()


def load_config(args):
    return json.loads(scripts.ensure_file(args.config).read_text())


class Alerts:

    @classmethod
    def make(cls, args):
        return cls(load_config(args)['alerts'])

    def __init__(self, config):
        # For now, only one destination `slack` is supported; so it has
        # to be present.
        self._dest_slack = DestinationSlack(config['destinations']['slack'])


class DestinationSlack:

    COLOR_TABLE = {
        Levels.INFO: '',
        Levels.GOOD: 'good',
        Levels.WARNING: 'warning',
        Levels.ERROR: 'danger',
    }

    @classmethod
    def make(cls, args):
        return cls(load_config(args)['alerts']['destinations']['slack'])

    def __init__(self, config):
        self.webhook = config['webhook']
        self.username = config.get('username', 'ops-onboard')
        self.icon_emoji = config.get('icon_emoji', ':robot_face:')

    def make_request(
            self, *,
            host,
            level,
            title,
            description):

        message = {
            'username': self.username,
            'icon_emoji': self.icon_emoji,
            'attachments': [
                {
                    'fallback': '%s: %s: %s: %s' % (
                        level.name,
                        host,
                        title,
                        description,
                    ),
                    'color': self.COLOR_TABLE[level],
                    'title': title,
                    'text': description,
                    'fields': [
                        {
                            'title': 'Host',
                            'value': host,
                            'short': True,
                        },
                    ],
                },
            ],
        }

        return urllib.request.Request(
            self.webhook,
            headers={'Content-Type': 'application/json'},
            data=json.dumps(message).encode('utf-8'),
        )

    def send(self, **kwargs):
        # urlopen checks the HTTP status code for us.
        urllib.request.urlopen(self.make_request(**kwargs))


@apps.with_help('send alert')
@apps.with_argument(
    '--host', default=os.uname().nodename,
    help='overwrite host name (default to %(default)s)',
)
@apps.with_argument(
    '--level',
    choices=tuple(level.name for level in Levels),
    default=Levels.INFO.name,
    help='set alert level (default to %(default)s)',
)
@apps.with_argument(
    '--systemd-service-result',
    help=(
        'provide service result for deriving alert level, '
        'overwriting `--level`'
    ),
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
    """Send alert to one of the destinations."""

    # At the moment we have only one destination.
    dest_slack = DestinationSlack.make(args)

    if args.systemd_service_result is not None:
        if args.systemd_service_result == 'success':
            level = Levels.GOOD
        else:
            level = Levels.ERROR
    else:
        level = Levels[args.level]

    dest_slack.send(
        host=args.host,
        level=level,
        title=args.title,
        description=args.description,
    )

    return 0


@apps.with_help('manage alerts')
@apps.with_defaults(no_locking_required=True)
@apps.with_argument(
    '--config', type=Path, default='/etc/ops/config.json',
    help='set config file path (default to %(default)s)'
)
@apps.with_apps(
    'operation', 'operation on alerts',
    send,
)
def alerts(args):
    """Manage alerts."""
    return args.operation(args)
