import unittest

from g1.operations.cores import alerts


class ConfigTest(unittest.TestCase):

    def test_destination_slack(self):
        with self.assertRaisesRegex(AssertionError, r'expect true'):
            alerts.Config.SlackDestination()

    def test_load_null(self):
        actual = alerts.Config.load_data(b'{"destination": {"kind": "null"}}')
        self.assertEqual(
            actual,
            alerts.Config(destination=alerts.Config.NullDestination()),
        )
        self.assertIsInstance(
            actual.destination,
            alerts.Config.NullDestination,
        )

    def test_load_slack(self):
        actual = alerts.Config.load_data(
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


if __name__ == '__main__':
    unittest.main()
