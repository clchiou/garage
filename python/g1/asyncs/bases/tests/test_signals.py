import unittest
import unittest.mock

from g1.asyncs import kernels
from g1.asyncs.bases import signals


class SignalSourceTest(unittest.TestCase):

    def setUp(self):
        path = signals.__name__ + '.signal'
        self.signal_mock = unittest.mock.patch(path).start()

    def tearDown(self):
        unittest.mock.patch.stopall()

    @kernels.with_kernel
    def test_singleton(self):
        self.assertIs(signals.SignalSource(), signals.SignalSource())

    @kernels.with_kernel
    def test_disallow_nested_use(self):
        source = signals.SignalSource()

        self.assertIsNone(source._wakeup_fd)
        self.assertEqual(source._handlers, {})

        with source:
            with self.assertRaises(AssertionError):
                with source:
                    pass

        self.assertIsNone(source._wakeup_fd)
        self.assertEqual(source._handlers, {})

        # But consecutive use is fine.
        with source:
            pass

        self.assertIsNone(source._wakeup_fd)
        self.assertEqual(source._handlers, {})

        self.signal_mock.signal.assert_not_called()
        self.signal_mock.siginterrupt.assert_not_called()

    @kernels.with_kernel
    def test_disallow_repeated_enable(self):
        with signals.SignalSource() as source:
            source.enable(0)
            with self.assertRaises(AssertionError):
                source.enable(0)
            source.disable(0)
            with self.assertRaises(AssertionError):
                source.disable(0)

    @kernels.with_kernel
    def test_get(self):
        with signals.SignalSource() as source:
            source._sock_w.send(b'\x02')
            kernels.run(source.get())
            self.signal_mock.Signals.assert_called_once_with(2)


if __name__ == '__main__':
    unittest.main()
