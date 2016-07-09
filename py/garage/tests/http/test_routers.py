import unittest

from garage.http.routers import ApiRouter


class RoutersTest(unittest.TestCase):

    def test_api_router_dispatch(self):
        router = ApiRouter(name='test-service', version=1)
        router.add_handler('point-1', 'point-1')
        router.add_handler('point-2', 'point-2')

        self.assertEqual('point-1', router.dispatch(b'/0/point-1'))
        self.assertEqual('point-1', router.dispatch(b'/1/point-1'))
        self.assertEqual('point-1', router.dispatch(b'/1/point-1?x=y'))
        self.assertEqual('point-1', router.dispatch(b'/1/point-1#p'))
        with self.assertRaises(ApiRouter.VersionNotSupported):
            router.dispatch(b'/2/point-1')

        self.assertEqual('point-2', router.dispatch(b'/0/point-2'))
        self.assertEqual('point-2', router.dispatch(b'/1/point-2'))
        with self.assertRaises(ApiRouter.VersionNotSupported):
            router.dispatch(b'/2/point-2')

        with self.assertRaises(ApiRouter.EndpointNotFound):
            router.dispatch(b'/point-1')  # No version.
        with self.assertRaises(ApiRouter.EndpointNotFound):
            router.dispatch(b'/0/')  # No endpoint.
        with self.assertRaises(ApiRouter.EndpointNotFound):
            router.dispatch(b'/-1/point-1')  # Incorrect version.
        with self.assertRaises(ApiRouter.EndpointNotFound):
            router.dispatch(b'/0/no-such-endpoint')


if __name__ == '__main__':
    unittest.main()
