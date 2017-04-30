import unittest

from tests.availability import http2_available

if http2_available:
    import http2
    from garage.http import servers


@unittest.skipUnless(http2_available, 'http2 unavailable')
class ServersTest(unittest.TestCase):

    def test_errors(self):
        with self.assertRaisesRegex(AssertionError, 'expect 4xx status'):
            servers.ClientError(http2.Status.INTERNAL_SERVER_ERROR)
        with self.assertRaisesRegex(AssertionError, 'expect 5xx status'):
            servers.ServerError(http2.Status.BAD_REQUEST)


if __name__ == '__main__':
    unittest.main()
