"""Manage alerts."""

__all__ = [
    'Config',
    'Message',
    'init',
    'load',
    'save',
    # Message sources.
    'process_collectd_notification',
    'watch_journal',
    'watch_syslog',
]

import dataclasses
import datetime
import enum
import json
import logging
import os
import re
import subprocess
import time
import typing
import urllib.error
import urllib.request
from pathlib import Path

from g1.bases import dataclasses as g1_dataclasses
from g1.bases import datetimes
from g1.bases import times
from g1.bases.assertions import ASSERT
from g1.containers import models as ctr_models
from g1.texts import jsons

from . import bases
from . import models

LOG = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class Message:

    class Levels(enum.Enum):
        INFO = enum.auto()
        GOOD = enum.auto()
        WARNING = enum.auto()
        ERROR = enum.auto()

    host: str
    level: Levels
    title: str
    description: str
    timestamp: datetime


@dataclasses.dataclass(frozen=True)
class Config:
    """Alert configuration.

    NOTE: The Config object is serialized and stored in a config file,
    and thus when you are updating the schema of the Config object, you
    should be careful about backward compatibility.
    """

    @dataclasses.dataclass(frozen=True)
    class Rule:
        """Log message filter rule.

        * pattern is a regular expression.  The captured groups of the
          expression (must be named) will be provided to the template.

        * template determines the action when the pattern matches the
          log message.  If it is None, no action is taken.  Otherwise a
          message is generated from the template and then sent.

        When generating the message, the captured groups is merged with
        the default "title" and "raw_message".
        """

        @dataclasses.dataclass(frozen=True)
        class Template:
            level: str
            title: str
            description: str

            def evaluate(self, kwargs):
                return {
                    'level':
                    Message.Levels[self.level.format(**kwargs).upper()],
                    'title': self.title.format(**kwargs),
                    'description': self.description.format(**kwargs),
                }

        pattern: str
        template: typing.Optional[Template] = None

    @dataclasses.dataclass(frozen=True)
    class Destination:
        kind: str

        def send(self, message):
            raise NotImplementedError

    @dataclasses.dataclass(frozen=True)
    class NullDestination(Destination):
        kind: str = 'null'

        def send(self, message):
            LOG.info('drop message: %s', message)

    @dataclasses.dataclass(frozen=True)
    class SlackDestination(Destination):

        _COLOR_TABLE = {
            Message.Levels.INFO: '',
            Message.Levels.GOOD: 'good',
            Message.Levels.WARNING: 'warning',
            Message.Levels.ERROR: 'danger',
        }

        kind: str = 'slack'
        webhook: str = ''
        username: str = 'ops'
        icon_emoji: str = ':robot_face:'

        def __post_init__(self):
            ASSERT.true(self.webhook)

        def send(self, message):
            try:
                # urlopen checks the HTTP status code for us.
                # pylint: disable=consider-using-with
                urllib.request.urlopen(self._make_request(message)).close()
            except urllib.error.HTTPError as exc:
                LOG.warning('cannot send to slack: %r', exc)

        def _make_request(self, message):
            data = {
                'username':
                self.username,
                'icon_emoji':
                self.icon_emoji,
                'attachments': [
                    {
                        'fallback':
                        '%s %s %s %s' % (
                            message.level.name,
                            message.host,
                            message.title,
                            message.description,
                        ),
                        'color':
                        self._COLOR_TABLE[message.level],
                        'title':
                        message.title,
                        'text':
                        message.description,
                        'fields': [
                            {
                                'title': 'Host',
                                'value': message.host,
                                'short': True,
                            },
                        ],
                        'ts':
                        int(message.timestamp.timestamp()),
                    },
                ],
            }
            return urllib.request.Request(
                self.webhook,
                headers={'Content-Type': 'application/json'},
                data=json.dumps(data).encode('utf-8'),
            )

    syslog_rules: typing.List[Rule] = dataclasses.field(
        default_factory=lambda: [
            Config.Rule(
                pattern=r'ERROR|FATAL',
                template=Config.Rule.Template(
                    level='ERROR',
                    title='{title}',
                    description='{raw_message}',
                ),
            ),
        ],
    )

    journal_rules: typing.List[Rule] = dataclasses.field(
        default_factory=lambda: [
            Config.Rule(
                pattern=r'ERROR|FATAL',
                template=Config.Rule.Template(
                    level='ERROR',
                    title='{title}',
                    description='{raw_message}',
                ),
            ),
        ],
    )

    # In addition to "title" and "raw_message", "host", "level", and
    # "timestamp" are also provided as defaults when generating the
    # message.
    collectd_rules: typing.List[Rule] = dataclasses.field(
        default_factory=lambda: [
            Config.Rule(
                pattern=r'',  # Match anything.
                template=Config.Rule.Template(
                    level='{level}',
                    title='{title}',
                    description='{raw_message}',
                ),
            ),
        ],
    )

    destination: Destination = NullDestination()

    @classmethod
    def load(cls, path):
        return cls._load_data(path.read_bytes())

    @classmethod
    def _load_data(cls, config_data):
        raw_config = json.loads(config_data)
        base_config = g1_dataclasses.fromdict(cls, raw_config)
        destination_type = Config.Destination
        if base_config.destination.kind == 'null':
            destination_type = Config.NullDestination
        elif base_config.destination.kind == 'slack':
            destination_type = Config.SlackDestination
        else:
            ASSERT.unreachable('unknown destination: {}', raw_config)
        return dataclasses.replace(
            base_config,
            destination=g1_dataclasses.fromdict(
                destination_type,
                raw_config['destination'],
            ),
        )

    def save(self, path):
        jsons.dump_dataobject(self, path)

    def send(self, message):
        return self.destination.send(message)


def init():
    alerts_path = _get_alerts_path()
    if alerts_path.exists():
        LOG.info('skip: alerts init: %s', alerts_path)
        return
    LOG.info('alerts init: %s', alerts_path)
    Config().save(alerts_path)
    bases.set_file_attrs(alerts_path)


def load(path=None):
    return Config.load(path if path is not None else _get_alerts_path())


def save(config):
    return config.save(_get_alerts_path())


def _get_alerts_path():
    return bases.get_repo_path() / models.REPO_ALERTS_FILENAME


#
# Message sources.
#


class _PipeProc:

    def __init__(self, cmd):
        self._cmd = cmd
        self._proc = None

    def __enter__(self):
        ASSERT.none(self._proc)
        self._proc = subprocess.Popen(self._cmd, stdout=subprocess.PIPE)
        return self._proc.stdout

    def __exit__(self, *_):
        for kill in (self._proc.terminate, self._proc.kill):
            if self._proc.poll() is not None:
                break
            kill()
            # TODO: Wait a little bit for signal delivery...  This seems
            # brittle.  How can we do better?
            time.sleep(0.2)
        if self._proc.poll() is None:
            raise RuntimeError('cannot stop process: %r' % self._proc)
        self._proc = None


def _compile_rules(rules):
    return [
        dataclasses.replace(rule, pattern=re.compile(rule.pattern))
        for rule in rules
    ]


def _search_rules(rules, raw_message):
    for rule in rules:
        match = rule.pattern.search(raw_message)
        if match is None:
            continue
        if rule.template is None:
            break
        return rule, match
    return None, None


def watch_syslog(config):
    rules = _compile_rules(config.syslog_rules)
    host = os.uname().nodename
    with _PipeProc([
        'tail',
        '--follow=name',
        '--retry',
        '--lines=0',
        '/var/log/syslog',
    ]) as pipe:
        while True:
            line = pipe.readline().decode('utf-8', errors='ignore')
            try:
                message = _parse_syslog_entry(rules, line.strip(), host)
            except (re.error, KeyError, ValueError) as exc:
                LOG.warning('syslog entry error: %r %r', exc, line)
                continue
            if message is not None:
                config.send(message)


def _parse_syslog_entry(rules, raw_message, host):
    rule, match = _search_rules(rules, raw_message)
    if rule is None:
        return None
    kwargs = match.groupdict()
    kwargs.setdefault('title', 'syslog')
    kwargs.setdefault('raw_message', raw_message)
    return Message(
        host=host,
        # TODO: Parse timestamp of log entry.
        timestamp=datetimes.utcnow(),
        **rule.template.evaluate(kwargs),
    )


_JOURNAL_BASE_DIR_PATH = Path('/var/log/journal')


def watch_journal(config, pod_id):
    journal_dir_path = (
        _JOURNAL_BASE_DIR_PATH / ctr_models.pod_id_to_machine_id(pod_id)
    )
    _wait_for_journal_dir(journal_dir_path)
    rules = _compile_rules(config.journal_rules)
    host = os.uname().nodename
    with _PipeProc([
        'journalctl',
        '--directory=%s' % journal_dir_path,
        '--follow',
        '--lines=0',
        '--output=json',
    ]) as pipe:
        while True:
            line = pipe.readline()
            try:
                entry = json.loads(line)
                message = _parse_journal_entry(rules, entry, host, pod_id)
            except json.JSONDecodeError as exc:
                LOG.warning('journal entry JSON decode error: %r %r', exc, line)
                continue
            except KeyError as exc:
                LOG.warning('journal entry key error: %r %r', exc, line)
                continue
            if message is not None:
                config.send(message)


def _wait_for_journal_dir(journal_dir_path):
    # It is possible that pod has not been created yet.
    check_counter = 0
    while not journal_dir_path.exists():
        if check_counter % 60 == 0:  # Log every minute.
            LOG.info('journal does not exist: %s', journal_dir_path)
        check_counter += 1
        time.sleep(1)


def _parse_journal_entry(rules, entry, host, pod_id):
    raw_message = entry['MESSAGE']
    if isinstance(raw_message, list):
        # It seems that, when there are non ASCII printable characters,
        # MESSAGE will be an array of byte values.
        raw_message = bytes(raw_message).decode('utf-8', errors='ignore')
    rule, match = _search_rules(rules, raw_message)
    if rule is None:
        return None
    kwargs = match.groupdict()
    kwargs.setdefault(
        'title',
        entry.get('SYSLOG_IDENTIFIER') \
        or entry.get('_SYSTEMD_UNIT')
        or entry.get('_HOSTNAME')
        or ctr_models.generate_machine_name(pod_id),
    )
    kwargs.setdefault('raw_message', raw_message)
    return Message(
        host=host,
        timestamp=_journal_get_timestamp(entry),
        **rule.template.evaluate(kwargs),
    )


def _journal_get_timestamp(entry):
    timestamp = (
        entry.get('_SOURCE_REALTIME_TIMESTAMP')
        or entry.get('__REALTIME_TIMESTAMP')
    )
    if timestamp is None:
        return datetimes.utcnow()
    return datetimes.utcfromtimestamp(
        times.convert(
            times.Units.MICROSECONDS,
            times.Units.SECONDS,
            int(timestamp),
        ),
    )


def process_collectd_notification(config, input_file):
    message = _parse_collectd_notification(
        _compile_rules(config.collectd_rules),
        input_file,
    )
    if message is not None:
        config.send(message)


_COLLECTD_SEVERITY_TABLE = {
    'OKAY': Message.Levels.GOOD.name,
    'WARNING': Message.Levels.WARNING.name,
    'FAILURE': Message.Levels.ERROR.name,
}

_COLLECTD_KNOWN_HEADERS = frozenset((
    'Plugin',
    'PluginInstance',
    'Type',
    'TypeInstance',
    'CurrentValue',
    'WarningMin',
    'WarningMax',
    'FailureMin',
    'FailureMax',
))


def _parse_collectd_notification(rules, input_file):
    kwargs = {
        'host': os.uname().nodename,
        'level': Message.Levels.INFO.name,
        'timestamp': datetimes.utcnow(),
    }
    headers = {}
    while True:
        header = input_file.readline().strip()
        if not header:
            break
        _parse_collectd_header(header, kwargs, headers)
    kwargs['title'] = _make_title_from_collectd_headers(headers)
    kwargs['raw_message'] = input_file.read()
    rule, match = _search_rules(rules, kwargs['raw_message'])
    if rule is None:
        return None
    kwargs.update(match.groupdict())
    return Message(
        host=kwargs['host'],
        timestamp=kwargs['timestamp'],
        **rule.template.evaluate(kwargs),
    )


def _parse_collectd_header(header, kwargs, headers):
    i = header.find(':')
    if i == -1:
        LOG.warning('ill-formatted collectd notification header: %s', header)
        return
    name = header[:i].strip()
    value = header[i + 1:].strip()
    if name == 'Host':
        kwargs['host'] = value
    elif name == 'Time':
        kwargs['timestamp'] = datetimes.utcfromtimestamp(float(value))
    elif name == 'Severity':
        level = _COLLECTD_SEVERITY_TABLE.get(value.upper())
        if level is None:
            LOG.warning('unknown collectd severity: %s', header)
        else:
            kwargs['level'] = level
    elif name in _COLLECTD_KNOWN_HEADERS:
        headers[name] = value
    else:
        LOG.warning('unknown collectd notification header: %s', header)


def _make_title_from_collectd_headers(headers):
    plugin = headers.get('Plugin')
    plugin_instance = headers.get('PluginInstance', '?')
    type_instance = headers.get('TypeInstance', '?')
    if plugin == 'cpu':
        who = 'cpu/%s/%s' % (plugin_instance, type_instance)
    elif plugin == 'memory':
        who = 'memory/%s' % type_instance
    elif plugin == 'df':
        who = 'df/%s/%s' % (plugin_instance, type_instance)
    else:
        # Unrecognizable plugin.
        return plugin or 'collectd notification'
    # NOTE: Any comparison to NaN is False.
    current_value = float(headers.get('CurrentValue', 'NaN'))
    warning_min = float(headers.get('WarningMin', 'NaN'))
    warning_max = float(headers.get('WarningMax', 'NaN'))
    failure_min = float(headers.get('FailureMin', 'NaN'))
    failure_max = float(headers.get('FailureMax', 'NaN'))
    if warning_min <= current_value <= warning_max:
        what = '%.2f <= %.2f <= %.2f' % (
            warning_min, current_value, warning_max
        )
    elif current_value > failure_max:
        what = '%.2f > %.2f' % (current_value, failure_max)
    elif current_value > warning_max:
        what = '%.2f > %.2f' % (current_value, warning_max)
    elif current_value < failure_min:
        what = '%.2f < %.2f' % (current_value, failure_min)
    elif current_value < warning_min:
        what = '%.2f < %.2f' % (current_value, warning_min)
    # Add these two in case of NaN.
    elif current_value <= warning_max:
        what = '%.2f <= %.2f' % (current_value, warning_max)
    elif current_value >= warning_min:
        what = '%.2f >= %.2f' % (current_value, warning_min)
    else:
        what = '%.2f' % current_value
    return '%s: %s' % (who, what)
