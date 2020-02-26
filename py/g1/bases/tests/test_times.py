import unittest

from g1.bases import times


class ConvertTest(unittest.TestCase):

    def test_convert(self):
        self.assertEqual(
            times.convert(times.Units.SECONDS, times.Units.SECONDS, 1.2),
            1.2,
        )
        self.assertEqual(
            times.convert(times.Units.SECONDS, times.Units.NANOSECONDS, 1.2),
            1_200_000_000,
        )
        self.assertEqual(
            times.convert(
                times.Units.MILLISECONDS, times.Units.NANOSECONDS, 1.2
            ),
            1_200_000,
        )
        self.assertEqual(
            times.convert(times.Units.MILLISECONDS, times.Units.SECONDS, 1.2),
            0.001_2,
        )
        self.assertEqual(
            times.convert(times.Units.MICROSECONDS, times.Units.SECONDS, 1.2),
            0.000_001_2,
        )


if __name__ == '__main__':
    unittest.main()
