import unittest

from garage.http.services import *


class ServiceHubTest(unittest.TestCase):

    def test_dispatch(self):
        hub = ServiceHub()

        s11 = Service(name='s1', version=1)
        s11.add_endpoint('p', 'p')
        s11.add_endpoint('q', 'q')
        hub.add_service(s11)

        s13 = Service(name='s1', version=3)
        s13.add_endpoint('p', 'p')
        s13.add_endpoint('r', 'r')
        hub.add_service(s13)

        s22 = Service(name='s2', version=2)
        s22.add_endpoint('p', 'p')
        hub.add_service(s22)

        self.assertDispatch(hub, b'/s1/0/p?x=y', s11, 'p')
        self.assertDispatch(hub, b'/s1/0/p#p', s11, 'p')

        self.assertDispatch(hub, b'/s1/0/p', s11, 'p')
        self.assertDispatch(hub, b'/s1/1/p', s11, 'p')
        self.assertDispatch(hub, b'/s1/0/q', s11, 'q')
        self.assertDispatch(hub, b'/s1/1/q', s11, 'q')
        with self.assertRaises(EndpointNotFound):
            hub.dispatch(b'/s1/0/r')
        with self.assertRaises(EndpointNotFound):
            hub.dispatch(b'/s1/1/r')

        self.assertDispatch(hub, b'/s1/2/p', s13, 'p')
        self.assertDispatch(hub, b'/s1/3/p', s13, 'p')
        with self.assertRaises(EndpointNotFound):
            hub.dispatch(b'/s1/2/q')
        with self.assertRaises(EndpointNotFound):
            hub.dispatch(b'/s1/3/q')
        self.assertDispatch(hub, b'/s1/2/r', s13, 'r')
        self.assertDispatch(hub, b'/s1/3/r', s13, 'r')

        with self.assertRaises(VersionNotSupported):
            hub.dispatch(b'/s1/4/p')
        with self.assertRaises(VersionNotSupported):
            hub.dispatch(b'/s1/4/q')
        with self.assertRaises(VersionNotSupported):
            hub.dispatch(b'/s1/4/r')

        self.assertDispatch(hub, b'/s2/0/p', s22, 'p')
        self.assertDispatch(hub, b'/s2/1/p', s22, 'p')
        self.assertDispatch(hub, b'/s2/2/p', s22, 'p')
        with self.assertRaises(VersionNotSupported):
            hub.dispatch(b'/s2/3/p')

        with self.assertRaises(EndpointNotFound):
            hub.dispatch(b'/0/p/')  # No service.
        with self.assertRaises(EndpointNotFound):
            hub.dispatch(b'/s1/0/')  # No endpoint.
        with self.assertRaises(EndpointNotFound):
            hub.dispatch(b'/s1/0/?x=y')  # No endpoint.
        with self.assertRaises(EndpointNotFound):
            hub.dispatch(b'/s1/0/#p')  # No endpoint.
        with self.assertRaises(EndpointNotFound):
            hub.dispatch(b'/s1/-1/p')  # Incorrect version.

    def assertDispatch(self, hub, path, service, endpoint):
        s, e = hub.dispatch(path)
        self.assertEqual(service, s)
        self.assertEqual(endpoint, e)


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
