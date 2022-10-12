import unittest
import unittest.mock

from g1.bases import loggings
from g1.bases import times


class LoggingsTest(unittest.TestCase):

    def test_once_per(self):
        once_per = loggings.OncePer()
        actual = []
        for i in range(10):
            once_per(3, actual.append, i)
        self.assertEqual(actual, [0, 3, 6, 9])

        actual = []
        for i in range(15):
            once_per(4, actual.append, i)
        self.assertEqual(actual, [0, 4, 8, 12])

        self.assertEqual(len(once_per._records), 2)
        for (location, record), expect_lineno, expect_record in zip(
            once_per._records.items(),
            (14, 19),
            (10, 15),
        ):
            self.assertRegex(location[0], r'tests/test_loggings.py$')
            self.assertEqual(location[1], expect_lineno)
            self.assertEqual(record, expect_record)

    @unittest.mock.patch.object(loggings, 'time')
    def test_check(self, mock_time):
        once_per = loggings.OncePer()

        actual = [once_per.check(3) for _ in range(10)]
        self.assertEqual(actual, [True, False, False] * 3 + [True])

        actual = [once_per.check(4) for _ in range(15)]
        self.assertEqual(
            actual,
            [True, False, False, False] * 3 + [True, False, False],
        )

        mock_time.monotonic_ns.side_effect = [1, 1000, 1001, 1002]
        actual = [
            once_per.check(1, times.Units.MICROSECONDS) for _ in range(4)
        ]
        self.assertEqual(actual, [True, False, True, False])

        self.assertEqual(len(once_per._records), 3)
        for (location, record), expect_lineno, expect_record in zip(
            once_per._records.items(),
            (36, 39, 47),
            (10, 15, 1001),
        ):
            self.assertRegex(location[0], r'tests/test_loggings.py$')
            self.assertEqual(location[1], expect_lineno)
            self.assertEqual(record, expect_record)


if __name__ == '__main__':
    unittest.main()
