import unittest

import datetime

from g1.bases import datetimes


class DatetimesTest(unittest.TestCase):

    def test_utcfromtimestamp(self):
        zero = datetime.datetime(1970, 1, 1, 0, 0)
        dt = datetimes.utcfromtimestamp(0)
        self.assertEqual(zero, dt.replace(tzinfo=None))
        self.assertEqual(0, dt.timestamp())


if __name__ == '__main__':
    unittest.main()
