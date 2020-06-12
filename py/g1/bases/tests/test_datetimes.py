import unittest

import datetime

from g1.bases import datetimes


class DatetimesTest(unittest.TestCase):

    def test_fromisoformat(self):
        self.assertEqual(
            datetimes.fromisoformat('2000-01-02T03:04:05'),
            datetime.datetime(
                2000, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc
            ),
        )
        self.assertEqual(
            datetimes.fromisoformat('2000-01-01T08:00:00+08:00'),
            datetime.datetime(
                2000, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc
            ),
        )

    def test_make_timestamp(self):
        dt = datetimes.make_timestamp(1970, 1, 1, 2, 3, 4)
        self.assertEqual(dt, datetimes.utcfromtimestamp(7200 + 180 + 4))
        self.assertEqual(
            dt,
            datetime.datetime(
                1970, 1, 1, 2, 3, 4, tzinfo=datetime.timezone.utc
            ),
        )

    def test_timestamp_date(self):
        dt = datetimes.utcfromtimestamp(7200 + 180 + 4)
        self.assertEqual(
            dt.replace(tzinfo=None), datetime.datetime(1970, 1, 1, 2, 3, 4)
        )
        self.assertEqual(dt.timestamp(), 7200 + 180 + 4)
        dt = datetimes.timestamp_date(dt)
        self.assertEqual(
            dt.replace(tzinfo=None), datetime.datetime(1970, 1, 1, 0, 0, 0)
        )
        self.assertEqual(dt.timestamp(), 0)

    def test_utcfromtimestamp(self):
        zero = datetime.datetime(1970, 1, 1)
        dt = datetimes.utcfromtimestamp(0)
        self.assertEqual(zero, dt.replace(tzinfo=None))
        self.assertEqual(0, dt.timestamp())


if __name__ == '__main__':
    unittest.main()
