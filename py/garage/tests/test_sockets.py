import unittest

from garage import sockets


class SocketsTest(unittest.TestCase):

    def test_cached_getaddrinfo(self):

        results = [1, 2, 3]

        def getaddrinfo_func(*args, **kwargs):
            return results.pop(0)

        cached_getaddrinfo = sockets.CachedGetaddrinfo(
            expiration=2,
            getaddrinfo_func=getaddrinfo_func,
        )

        self.assertEqual(1, cached_getaddrinfo('localhost', 80))
        self.assertEqual(1, cached_getaddrinfo('localhost', 80))
        self.assertEqual(2, cached_getaddrinfo('localhost', 80))
        self.assertEqual(2, cached_getaddrinfo('localhost', 80))
        self.assertEqual(3, cached_getaddrinfo('localhost', 80))
        self.assertEqual(3, cached_getaddrinfo('localhost', 80))


if __name__ == '__main__':
    unittest.main()
