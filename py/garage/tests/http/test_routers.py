import unittest

from tests.availability import http2_available

if http2_available:
    from garage.http.routers import ApiRouter, PrefixRouter
    from garage.http.servers import ClientError


@unittest.skipUnless(http2_available, 'http2 unavailable')
class RoutersTest(unittest.TestCase):

    def test_api_router(self):
        router = ApiRouter(name='test-service', version=1)
        router.add_handler('point-1', 'point-1')
        router.add_handler('point-2', 'point-2')

        self.assertEqual('point-1', router.route(b'/0/point-1'))
        self.assertEqual('point-1', router.route(b'/1/point-1'))
        self.assertEqual('point-1', router.route(b'/1/point-1?x=y'))
        self.assertEqual('point-1', router.route(b'/1/point-1#p'))
        with self.assertRaises(ApiRouter.VersionNotSupported):
            router.route(b'/2/point-1')

        self.assertEqual('point-2', router.route(b'/0/point-2'))
        self.assertEqual('point-2', router.route(b'/1/point-2'))
        with self.assertRaises(ApiRouter.VersionNotSupported):
            router.route(b'/2/point-2')

        with self.assertRaises(ApiRouter.EndpointNotFound):
            router.route(b'/point-1')  # No version.
        with self.assertRaises(ApiRouter.EndpointNotFound):
            router.route(b'/0/')  # No endpoint.
        with self.assertRaises(ApiRouter.EndpointNotFound):
            router.route(b'/-1/point-1')  # Incorrect version.
        with self.assertRaises(ApiRouter.EndpointNotFound):
            router.route(b'/0/no-such-endpoint')

        router.root_path = '/root-path'
        self.assertEqual('point-1', router.route(b'/root-path/0/point-1'))

    def test_prefix_router(self):
        router = PrefixRouter()
        router.add_handler('GET', '/prefix/1', 'handler-1')
        router.add_handler('POST', '/prefix/1', 'handler-2')
        router.add_handler('GET', '/prefix', 'handler-3')

        self.assertEqual(
            'handler-1', router.route(b'GET', b'/prefix/1'))
        self.assertEqual(
            'handler-1', router.route(b'GET', b'/prefix/1-something'))

        self.assertEqual(
            'handler-2', router.route(b'POST', b'/prefix/1'))
        self.assertEqual(
            'handler-2', router.route(b'POST', b'/prefix/1-something'))

        self.assertEqual(
            'handler-3', router.route(b'GET', b'/prefix'))

        with self.assertRaisesRegex(ClientError, 'method not allowed'):
            router.route(b'PUT', b'/prefix/1')

        with self.assertRaisesRegex(ClientError, 'no match path prefix'):
            router.route(b'GET', b'/no-such-prefix')

    def test_prefix_router_hidden(self):
        router = PrefixRouter()
        router.add_handler('GET', '/a', 'handler-1')
        with self.assertRaisesRegex(
                AssertionError, r'prefix b\'/a/b\' is hidden'):
            router.add_handler('GET', '/a/b', 'handler-1')


if __name__ == '__main__':
    unittest.main()
