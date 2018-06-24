__all__ = [
    'alerts',
]

from pathlib import Path
import contextlib
import datetime
import enum
import fcntl
import json
import logging
import os
import re
import selectors
import subprocess
import sys
import urllib.request

from garage import apps
from garage import scripts
from garage.assertions import ASSERT


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
        self._srcs = [
            SourceLog(src_config)
            for src_config in config['sources']
        ]
        # For now, only one destination `slack` is supported; so it has
        # to be present.
        self._dst_slack = DestinationSlack(config['destinations']['slack'])

    def watch(self):
        selector = selectors.DefaultSelector()
        with contextlib.ExitStack() as stack:
            for src in self._srcs:
                pipe = stack.enter_context(src.tailing())
                self._set_nonblocking(pipe)
                selector.register(pipe, selectors.EVENT_READ, src)
            while True:
                for key, _ in selector.select():
                    src = key.data
                    message = src.parse(key.fileobj)
                    if message is not None:
                        self._dst_slack.send(message)

    @staticmethod
    def _set_nonblocking(pipe):
        # NOTE: Use fcntl is not portable to non-Unix platforms.
        fd = pipe.fileno()
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)


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

    @staticmethod
    def _make_title(headers, default):
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


class SourceLog:

    class Tailing:

        def __init__(self, path):
            self.path = path
            self._proc = None

        def __enter__(self):
            ASSERT.none(self._proc)
            cmd = ['tail', '-Fn0', self.path]
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
            return self._proc.stdout

        def __exit__(self, *_):
            for kill in (self._proc.terminate, self._proc.kill):
                if self._proc.poll() is None:
                    kill()
                    self._proc.wait(2)
                else:
                    break
            if self._proc.poll() is None:
                raise RuntimeError('cannot stop process: %r', self._proc)
            self._proc = None

    def __init__(self, config):
        self.path = config['path']
        self._rules = [
            (re.compile(rule['pattern']), rule.get('alert', {}))
            for rule in config['rules']
        ]
        ASSERT(self._rules, 'expect non-empty rules: %r', config)

    def tailing(self):
        return self.Tailing(self.path)

    def parse(self, alert_input):
        line = alert_input.readline().decode('utf-8').strip()
        for pattern, alert in self._rules:
            match = pattern.search(line)
            if match:
                return self._make_message(alert, match, line)
        return None

    def _make_message(self, alert, match, line):

        kwargs = match.groupdict()
        kwargs.setdefault('host', os.uname().nodename)
        kwargs.setdefault('title', self.path)
        kwargs.setdefault('raw_message', line)

        message = {
            'host':
                alert.get('host', '{host}').format(**kwargs),
            'level':
                Levels[alert.get('level', 'INFO').format(**kwargs).upper()],
            'title':
                alert.get('title', '{title}').format(**kwargs),
            'description':
                alert.get('description', '{raw_message}').format(**kwargs),
        }

        timestamp_fmt = alert.get('timestamp')
        if timestamp_fmt is not None:
            value = float(timestamp_fmt.format(**kwargs))
            message['timestamp'] = datetime.datetime.utcfromtimestamp(value)

        return message


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

    def send(self, message):
        # urlopen checks the HTTP status code for us.
        urllib.request.urlopen(self._make_request(**message))

    def _make_request(
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
        dst_slack.send(message)

    return 0


@apps.with_help('send alert')
@apps.with_argument(
    '--host', default=os.uname().nodename,
    help='overwrite host name (default to %(default)s)',
)
@apps.with_argument(
    '--level',
    choices=tuple(level.name.lower() for level in Levels),
    default=Levels.INFO.name.lower(),
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
        level = Levels[args.level.upper()]

    dst_slack.send(dict(
        host=args.host,
        level=level,
        title=args.title,
        description=args.description,
        timestamp=datetime.datetime.utcnow(),
    ))

    return 0


@apps.with_help('watch the system and generate alerts')
def watch(args):
    """Watch the system and generate alerts.

    This is intended to be the most basic layer of the alerting system;
    more sophisticated alerting logic should be implemented at higher
    level.
    """
    Alerts.make(args).watch()
    return 0


@apps.with_help('manage alerts')
@apps.with_defaults(
    no_locking_required=True,
    root_allowed=True,
)
@apps.with_argument(
    '--config', type=Path, default='/etc/ops/config.json',
    help='set config file path (default to %(default)s)'
)
@apps.with_apps(
    'operation', 'operation on alerts',
    collectd,
    send,
    watch,
)
def alerts(args):
    """Manage alerts."""
    return args.operation(args)
