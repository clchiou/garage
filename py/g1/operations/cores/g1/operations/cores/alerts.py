"""Manage alerts."""

__all__ = [
    'Config',
    'Message',
    'init',
    'load',
    'save',
]

import dataclasses
import datetime
import enum
import json
import logging
import urllib.error
import urllib.request

from g1.bases import dataclasses as g1_dataclasses
from g1.bases.assertions import ASSERT
from g1.texts import jsons

from . import bases
from . import models

LOG = logging.getLogger(__name__)

_CONFIG_FILENAME = 'alerts'


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
                urllib.request.urlopen(self._make_request(message))
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

    destination: Destination

    @classmethod
    def load(cls, path):
        return cls.load_data(path.read_bytes())

    @classmethod
    def load_data(cls, config_data):
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
    bases.make_dir(alerts_path.parent)
    if alerts_path.exists():
        LOG.info('skip: alerts init: %s', alerts_path)
        return
    LOG.info('alerts init: %s', alerts_path)
    Config(destination=Config.NullDestination()).save(alerts_path)
    bases.set_file_attrs(alerts_path)


def load(path=None):
    return Config.load(path if path is not None else _get_alerts_path())


def save(config):
    return config.save(_get_alerts_path())


def _get_alerts_path():
    return (
        bases.get_repo_path() / \
        models.REPO_ALERTS_DIR_NAME /
        _CONFIG_FILENAME
    )
