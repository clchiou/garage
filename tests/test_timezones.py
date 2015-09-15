import unittest

import datetime

from garage.timezones import TimeZone


class TimeZoneTest(unittest.TestCase):

    def test_time_zone(self):
        utc = datetime.datetime(2000, 1, 2, 3, 4, 0, 0, TimeZone.UTC)
        cst = utc.astimezone(TimeZone.CST)
        self.assertEqual(2000, cst.year)
        self.assertEqual(1, cst.month)
        self.assertEqual(2, cst.day)
        self.assertEqual(11, cst.hour)
        self.assertEqual(4, cst.minute)
        self.assertEqual(0, cst.second)
        self.assertEqual(0, cst.microsecond)


if __name__ == '__main__':
    unittest.main()

