import unittest

from datetime import datetime

from garage import datetimes
from garage.timezones import TimeZone


class DatetimesTest(unittest.TestCase):

    def test_datetimes(self):
        dt_obj = datetime(2000, 1, 2, 3, 4, 0, 0, TimeZone.CST)
        dt_str = datetimes.format_iso8601(dt_obj)
        self.assertEqual('2000-01-02T03:04:00.000000+0800', dt_str)
        self.assertEqual(dt_obj, datetimes.parse_iso8601(dt_str))

    def test_fromtimestamp(self):
        zero = datetime(1970, 1, 1, 0, 0)

        # We do not use the implicit local timezone like stdlib (which
        # will surprise you).
        dt = datetimes.utcfromtimestamp(0)
        self.assertEqual(zero, dt.replace(tzinfo=None))
        self.assertEqual(0, dt.timestamp())


if __name__ == '__main__':
    unittest.main()
