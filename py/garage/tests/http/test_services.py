import unittest

from garage.http.services import *


class ServiceTest(unittest.TestCase):

    def test_dispatch(self):
        service = Service(name='test-service', version=1)
        service.add_endpoint('point-1', 'point-1')
        service.add_endpoint('point-2', 'point-2')

        self.assertEqual('point-1', service.dispatch(b'/0/point-1'))
        self.assertEqual('point-1', service.dispatch(b'/1/point-1'))
        self.assertEqual('point-1', service.dispatch(b'/1/point-1?x=y'))
        self.assertEqual('point-1', service.dispatch(b'/1/point-1#p'))
        with self.assertRaises(VersionNotSupported):
            service.dispatch(b'/2/point-1')

        self.assertEqual('point-2', service.dispatch(b'/0/point-2'))
        self.assertEqual('point-2', service.dispatch(b'/1/point-2'))
        with self.assertRaises(VersionNotSupported):
            service.dispatch(b'/2/point-2')

        with self.assertRaises(EndpointNotFound):
            service.dispatch(b'/point-1')  # No version.
        with self.assertRaises(EndpointNotFound):
            service.dispatch(b'/0/')  # No endpoint.
        with self.assertRaises(EndpointNotFound):
            service.dispatch(b'/-1/point-1')  # Incorrect version.
        with self.assertRaises(EndpointNotFound):
            service.dispatch(b'/0/no-such-endpoint')


if __name__ == '__main__':
    unittest.main()
