__all__ = [
    'alerts',
]

from pathlib import Path
import datetime
import enum
import json
import logging
import os
import sys
import urllib.request

from garage import apps
from garage import scripts


LOG = logging.getLogger(__name__)


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


class SourceCollectd:

    SEVERITY_TABLE = {
        'OKAY': Levels.GOOD,
        'WARNING': Levels.WARNING,
        'FAILURE': Levels.ERROR,
    }

    DEFAULT_TITLE = 'collectd notification'

    def parse(self, alert_input):
        message = {'level': Levels.INFO}
        headers = {}
        while True:
            line = alert_input.readline().strip()
            if line:
                self._parse_header(line, message, headers)
            else:
                break  # No more header fields.
        message['title'] = self._make_title(headers, self.DEFAULT_TITLE)
        message['description'] = alert_input.read()
        return message

    def _parse_header(self, line, message, headers):
        name, value = line.split(':', maxsplit=1)
        name = name.strip()
        value = value.strip()

        if name == 'Host':
            message['host'] = value
        elif name == 'Time':
            value = float(value)
            message['timestamp'] = datetime.datetime.utcfromtimestamp(value)
        elif name == 'Severity':
            message['level'] = self.SEVERITY_TABLE.get(value, Levels.INFO)

        elif name == 'Plugin':
            headers['plugin'] = value
        elif name == 'PlugIninstance':
            headers['plugin_instance'] = value

        elif name == 'Type':
            headers['type'] = value
        elif name == 'TypeInstance':
            headers['type_instance'] = value

        elif name == 'CurrentValue':
            headers['current_value'] = float(value)

        elif name == 'WarningMin':
            headers['warning_min'] = float(value)
        elif name == 'WarningMax':
            headers['warning_max'] = float(value)

        elif name == 'FailureMin':
            headers['failure_min'] = float(value)
        elif name == 'FailureMax':
            headers['failure_max'] = float(value)

        else:
            LOG.error('unknown collectd notification header: %r', line)

    def _make_title(self, headers, default):
        """Generate title string for certain plugins."""

        plugin = headers.get('plugin')
        plugin_instance = headers.get('plugin_instance', '?')
        type_instance = headers.get('type_instance', '?')
        if plugin == 'cpu':
            who = 'cpu:%s,%s' % (plugin_instance, type_instance)
        elif plugin == 'memory':
            who = 'memory,%s' % type_instance
        elif plugin == 'df':
            who = 'df:%s,%s' % (plugin_instance, type_instance)
        else:
            return default

        # NOTE: We make use of the property that any comparison to NaN
        # is False.
        nan = float('NaN')
        current_value = headers.get('current_value', nan)
        failure_min = headers.get('failure_min', nan)
        failure_max = headers.get('failure_max', nan)
        warning_min = headers.get('warning_min', nan)
        warning_max = headers.get('warning_max', nan)

        if warning_min <= current_value <= warning_max:
            what = '%.2f%% <= %.2f%% <= %.2f%%' % (
                warning_min, current_value, warning_max)

        elif current_value > failure_max:
            what = '%.2f%% > %.2f%%' % (current_value, failure_max)
        elif current_value > warning_max:
            what = '%.2f%% > %.2f%%' % (current_value, warning_max)
        elif current_value <= warning_max:
            what = '%.2f%% <= %.2f%%' % (current_value, warning_max)

        elif current_value < failure_min:
            what = '%.2f%% < %.2f%%' % (current_value, failure_min)
        elif current_value < warning_min:
            what = '%.2f%% < %.2f%%' % (current_value, warning_min)
        elif current_value >= warning_min:
            what = '%.2f%% >= %.2f%%' % (current_value, warning_min)

        else:
            what = '?'

        return '%s: %s' % (who, what)


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
            host=None,
            timestamp=None,
            level,
            title,
            description):

        fallback = [level.name]
        if host:
            fallback.append(host)
        fallback.append(title)
        fallback.append(description)
        fallback = ': '.join(fallback)

        fields = []
        if host:
            fields.append({
                'title': 'Host',
                'value': host,
                'short': True,
            })

        attachment = {
            'fallback': fallback,
            'color': self.COLOR_TABLE[level],
            'title': title,
            'text': description,
            'fields': fields,
        }
        if timestamp is not None:
            attachment['ts'] = int(timestamp.timestamp())

        message = {
            'username': self.username,
            'icon_emoji': self.icon_emoji,
            'attachments': [attachment],
        }

        return urllib.request.Request(
            self.webhook,
            headers={'Content-Type': 'application/json'},
            data=json.dumps(message).encode('utf-8'),
        )

    def send(self, **kwargs):
        # urlopen checks the HTTP status code for us.
        urllib.request.urlopen(self.make_request(**kwargs))


@apps.with_help('generate alert from collectd notification')
def collectd(args):
    """Generate an alert from collectd notification and then send it."""

    # At the moment we have only one destination.
    dst_slack = DestinationSlack.make(args)
    dst_slack.username = 'collectd'
    dst_slack.icon_emoji = ':exclamation:'

    src_collectd = SourceCollectd()
    message = src_collectd.parse(sys.stdin)

    if message:
        dst_slack.send(**message)

    return 0


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
    dst_slack = DestinationSlack.make(args)

    if args.systemd_service_result is not None:
        if args.systemd_service_result == 'success':
            level = Levels.GOOD
        else:
            level = Levels.ERROR
    else:
        level = Levels[args.level]

    dst_slack.send(
        host=args.host,
        level=level,
        title=args.title,
        description=args.description,
        timestamp=datetime.datetime.utcnow(),
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
    collectd,
    send,
)
def alerts(args):
    """Manage alerts."""
    return args.operation(args)
