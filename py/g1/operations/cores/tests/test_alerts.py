import unittest
import unittest.mock

import io
import re

from g1.bases import datetimes
from g1.operations.cores import alerts


class ConfigTest(unittest.TestCase):

    def test_destination_slack(self):
        with self.assertRaisesRegex(AssertionError, r'expect true'):
            alerts.Config.SlackDestination()

    def test_load_null(self):
        actual = alerts.Config._load_data(b'{"destination": {"kind": "null"}}')
        self.assertEqual(
            actual,
            alerts.Config(destination=alerts.Config.NullDestination()),
        )
        self.assertIsInstance(
            actual.destination,
            alerts.Config.NullDestination,
        )

    def test_load_slack(self):
        actual = alerts.Config._load_data(
            b'{"destination": {"kind": "slack", "webhook": "x"}}'
        )
        self.assertEqual(
            actual,
            alerts.Config(
                destination=alerts.Config.SlackDestination(webhook='x'),
            ),
        )
        self.assertIsInstance(
            actual.destination,
            alerts.Config.SlackDestination,
        )


class SyslogTest(unittest.TestCase):

    @unittest.mock.patch.object(alerts, 'datetimes')
    def test_parse_syslog_entry(self, mock_datetimes):
        mock_datetimes.utcnow.return_value = None
        self.assertEqual(
            alerts._parse_syslog_entry(
                [
                    alerts.Config.Rule(
                        pattern=re.compile(r'does not match'),
                        template=None,
                    ),
                    alerts.Config.Rule(
                        pattern=re.
                        compile(r'(?P<level>ERROR) (?P<raw_message>.*)'),
                        template=alerts.Config.Rule.Template(
                            level='{level}',
                            title='{title}',
                            description='{raw_message}',
                        ),
                    ),
                ],
                'some prefix ERROR this is an error message',
                'foobar',
            ),
            alerts.Message(
                host='foobar',
                level=alerts.Message.Levels.ERROR,
                title='syslog',
                description='this is an error message',
                timestamp=None,
            ),
        )


class JournalTest(unittest.TestCase):

    def test_parse_journal_entry(self):
        self.assertIsNone(
            alerts._parse_journal_entry(
                [
                    alerts.Config.Rule(
                        pattern=re.compile(r'something'),
                        template=alerts.Config.Rule.Template(
                            level='ERROR',
                            title='{title}',
                            description='{raw_message}',
                        ),
                    )
                ],
                {'MESSAGE': 'no match'},
                'foobar',
                '01234567-89ab-cdef-0123-456789abcdef',
            )
        )
        self.assertIsNone(
            alerts._parse_journal_entry(
                [
                    alerts.Config.Rule(
                        pattern=re.compile(r'something'),
                        template=None,
                    )
                ],
                {'MESSAGE': 'this has something'},
                'foobar',
                '01234567-89ab-cdef-0123-456789abcdef',
            )
        )
        self.assertEqual(
            alerts._parse_journal_entry(
                [
                    alerts.Config.Rule(
                        pattern=re.compile(
                            r'(?P<level>INFO) '
                            r'this (?P<raw_message>.* something)'
                        ),
                        template=alerts.Config.Rule.Template(
                            level='{level}',
                            title='{title}',
                            description='{raw_message}',
                        ),
                    )
                ],
                {
                    'SYSLOG_IDENTIFIER': 'spam',
                    'MESSAGE': 'INFO this has something',
                    '_SOURCE_REALTIME_TIMESTAMP': '1001200200',
                },
                'foobar',
                '01234567-89ab-cdef-0123-456789abcdef',
            ),
            alerts.Message(
                host='foobar',
                level=alerts.Message.Levels.INFO,
                title='spam',
                description='has something',
                timestamp=datetimes.utcfromtimestamp(1001.2002),
            ),
        )


class CollectdTest(unittest.TestCase):

    def test_parse_collectd_notification(self):
        self.assertEqual(
            alerts.parse_collectd_notification(
                io.StringIO(
                    '''\
Severity: OKAY
Time: 1234.567
Host: foobar
Plugin: cpu
PluginInstance: 0
Type: cpu
TypeInstance: idle
DataSource: value
CurrentValue: 2.000000e+01
WarningMin: 1.000000e+01
WarningMax: nan
FailureMin: 5.000000e+00
FailureMax: nan

Some message.
Second line of message.
'''
                )
            ),
            alerts.Message(
                host='foobar',
                level=alerts.Message.Levels.GOOD,
                title='cpu/0/idle: 20.00 >= 10.00',
                description='Some message.\nSecond line of message.\n',
                timestamp=datetimes.utcfromtimestamp(1234.567),
            ),
        )

    def test_make_title_from_collectd_headers(self):
        self.assertEqual(
            alerts._make_title_from_collectd_headers({
                'Plugin': 'foobar',
            }),
            'foobar',
        )
        self.assertEqual(
            alerts._make_title_from_collectd_headers({
                'Plugin': 'cpu',
            }),
            'cpu/?/?: nan',
        )
        for current_value, expect in [
            ('20', 'cpu/0/idle: 20.00 < 30.00'),
            ('30', 'cpu/0/idle: 30.00 < 40.00'),
            ('50', 'cpu/0/idle: 40.00 <= 50.00 <= 60.00'),
            ('70', 'cpu/0/idle: 70.00 > 60.00'),
            ('80', 'cpu/0/idle: 80.00 > 70.00'),
        ]:
            with self.subTest((current_value, expect)):
                self.assertEqual(
                    alerts._make_title_from_collectd_headers({
                        'Plugin':
                        'cpu',
                        'PluginInstance':
                        '0',
                        'TypeInstance':
                        'idle',
                        'CurrentValue':
                        current_value,
                        'FailureMin':
                        '30',
                        'WarningMin':
                        '40',
                        'WarningMax':
                        '60',
                        'FailureMax':
                        '70',
                    }),
                    expect,
                )
        for current_value, expect in [
            ('20', 'cpu/?/?: 20.00 <= 60.00'),
            ('30', 'cpu/?/?: 30.00 <= 60.00'),
            ('50', 'cpu/?/?: 50.00 <= 60.00'),
            ('70', 'cpu/?/?: 70.00 > 60.00'),
            ('80', 'cpu/?/?: 80.00 > 70.00'),
        ]:
            with self.subTest((current_value, expect)):
                self.assertEqual(
                    alerts._make_title_from_collectd_headers({
                        'Plugin':
                        'cpu',
                        'CurrentValue':
                        current_value,
                        'FailureMin':
                        'nan',
                        'WarningMin':
                        'nan',
                        'WarningMax':
                        '60',
                        'FailureMax':
                        '70',
                    }),
                    expect,
                )
        for current_value, expect in [
            ('20', 'cpu/?/?: 20.00 < 30.00'),
            ('30', 'cpu/?/?: 30.00 < 40.00'),
            ('50', 'cpu/?/?: 50.00 >= 40.00'),
            ('70', 'cpu/?/?: 70.00 >= 40.00'),
            ('80', 'cpu/?/?: 80.00 >= 40.00'),
        ]:
            with self.subTest((current_value, expect)):
                self.assertEqual(
                    alerts._make_title_from_collectd_headers({
                        'Plugin':
                        'cpu',
                        'CurrentValue':
                        current_value,
                        'FailureMin':
                        '30',
                        'WarningMin':
                        '40',
                        'WarningMax':
                        'nan',
                        'FailureMax':
                        'nan',
                    }),
                    expect,
                )


if __name__ == '__main__':
    unittest.main()
