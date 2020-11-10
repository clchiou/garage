import unittest

from g1.bases import loggings


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

        self.assertEqual(len(once_per._num_calls), 2)
        for (location, num_calls), expect_lineno, expect_num_calls in zip(
            once_per._num_calls.items(),
            (12, 17),
            (10, 15),
        ):
            self.assertRegex(location[0], r'tests/test_loggings.py$')
            self.assertEqual(location[1], expect_lineno)
            self.assertEqual(num_calls, expect_num_calls)


if __name__ == '__main__':
    unittest.main()
