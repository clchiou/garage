import unittest
import unittest.mock

from g1.bases import timers


class TimersTest(unittest.TestCase):

    @unittest.mock.patch('time.monotonic')
    def test_get_timeout_positive(self, monotonic_mock):
        monotonic_mock.side_effect = [10, 20, 30]
        timer = timers.Timer(14)
        self.assertEqual(timer.get_timeout(), 4)
        self.assertEqual(timer.get_timeout(), -6)

    @unittest.mock.patch('time.monotonic')
    def test_is_expired_positive(self, monotonic_mock):
        monotonic_mock.side_effect = [10, 20, 30]
        timer = timers.Timer(14)
        self.assertFalse(timer.is_expired())
        self.assertTrue(timer.is_expired())

    @unittest.mock.patch('time.monotonic')
    def test_get_timeout_non_positive(self, monotonic_mock):
        for timeout, expects in [(0, (-10, -20)), (-1, (-11, -21))]:
            with self.subTest(check=timeout):
                monotonic_mock.side_effect = [10, 20, 30]
                timer = timers.Timer(timeout)
                for expect in expects:
                    self.assertEqual(timer.get_timeout(), expect)

    @unittest.mock.patch('time.monotonic')
    def test_is_expired_non_positive(self, monotonic_mock):
        for timeout in (0, -1):
            with self.subTest(check=timeout):
                monotonic_mock.side_effect = [10, 20, 30]
                timer = timers.Timer(timeout)
                self.assertTrue(timer.is_expired())

    @unittest.mock.patch('time.monotonic')
    def test_start(self, monotonic_mock):
        monotonic_mock.side_effect = [10, 11, 20, 30]
        timer = timers.Timer(14)
        timer.start()
        self.assertEqual(timer.get_timeout(), 5)
        self.assertEqual(timer.get_timeout(), -5)

    @unittest.mock.patch('time.monotonic')
    def test_stop(self, monotonic_mock):
        monotonic_mock.side_effect = [10, 11, 15, 20, 30]
        timer = timers.Timer(14)
        self.assertEqual(timer._timeout, 14)
        timer.stop()
        self.assertEqual(timer._timeout, 13)
        timer.start()
        self.assertEqual(timer.get_timeout(), 8)
        self.assertEqual(timer.get_timeout(), -2)

    @unittest.mock.patch('time.monotonic')
    def test_overflow(self, monotonic_mock):
        monotonic_mock.side_effect = [10, 5]
        timer = timers.Timer(10)
        with self.assertRaisesRegex(AssertionError, r'expect x > 10'):
            timer.get_timeout()

    def test_not_started(self):
        timer = timers.Timer(10)
        self.assertTrue(timer._started)
        timer.stop()
        self.assertFalse(timer._started)
        with self.assertRaisesRegex(AssertionError, r'expect true-value'):
            timer.get_timeout()


if __name__ == '__main__':
    unittest.main()
