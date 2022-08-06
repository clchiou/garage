import unittest
import unittest.mock

from g1.asyncs import kernels
from g1.bases import contexts
from g1.webs import consts
from g1.webs import wsgi_apps
from g1.webs.handlers import requests


class RateLimiterTest(unittest.TestCase):

    @kernels.with_kernel
    @unittest.mock.patch.object(requests.time, 'monotonic')
    def test_rate_limiter(self, mock_monotonic):
        mock_monotonic.return_value = 0
        handler = requests.RateLimiter(
            token_rate=2,
            bucket_size=5,
            get_bucket_key=lambda _: 'key',
        )

        kernels.run(handler(None, None))
        self.assertEqual(handler._buckets['key']._num_tokens, 4)

        mock_monotonic.return_value = 0.5
        kernels.run(handler(None, None))
        self.assertEqual(handler._buckets['key']._num_tokens, 4)

        for expect in [3, 2, 1, 0]:
            kernels.run(handler(None, None))
            self.assertEqual(handler._buckets['key']._num_tokens, expect)

        with self.assertRaisesRegex(
            wsgi_apps.HttpError,
            r'rate limit exceeded: bucket_key=\'key\' retry_after=2.5',
        ) as cm:
            kernels.run(handler(None, None))
        self.assertIs(cm.exception.status, consts.Statuses.TOO_MANY_REQUESTS)
        self.assertEqual(
            cm.exception.headers, {consts.HEADER_RETRY_AFTER: '3'}
        )


class TokenBucketTest(unittest.TestCase):

    @unittest.mock.patch.object(requests.time, 'monotonic')
    def test_maybe_remove(self, mock_monotonic):
        mock_monotonic.return_value = 0
        bucket = requests.TokenBucket(2, 5)
        self.assertEqual(bucket._num_tokens, 5)

        self.assertIsNone(bucket.maybe_remove(5))
        self.assertEqual(bucket._num_tokens, 0)

        mock_monotonic.return_value = 1
        self.assertIsNone(bucket.maybe_remove(1))
        self.assertEqual(bucket._num_tokens, 1)

        self.assertEqual(bucket.maybe_remove(2), 2.5)
        self.assertEqual(bucket._num_tokens, 1)

    @unittest.mock.patch.object(requests.time, 'monotonic')
    def test_add_tokens(self, mock_monotonic):
        mock_monotonic.return_value = 0
        bucket = requests.TokenBucket(2, 5)
        self.assertEqual(bucket._num_tokens, 5)
        bucket._num_tokens = 0

        bucket._add_tokens()
        self.assertEqual(bucket._num_tokens, 0)

        mock_monotonic.return_value = 1
        bucket._add_tokens()
        self.assertEqual(bucket._num_tokens, 2)

        mock_monotonic.return_value = 2
        bucket._add_tokens()
        self.assertEqual(bucket._num_tokens, 4)

        mock_monotonic.return_value = 3
        bucket._add_tokens()
        self.assertEqual(bucket._num_tokens, 5)

        mock_monotonic.return_value = 4
        bucket._add_tokens()
        self.assertEqual(bucket._num_tokens, 5)


class ParseAcceptLanguageTest(unittest.TestCase):

    def test_parse_accept_language_empty(self):
        request = wsgi_apps.Request(environ={}, context=contexts.Context())
        self.assertEqual(requests.parse_accept_language(request), [])

    def test_parse_accept_language(self):
        for header, expect in [
            ('  *  ', [('*', 1.0)]),
            (
                '  en-US  ,  en  ;  q=0.5  ,  *;q=1.000  ',
                [
                    (['en', 'US'], 1.0),
                    ('*', 1.0),
                    (['en'], 0.5),
                ],
            ),
        ]:
            with self.subTest((header, expect)):
                request = wsgi_apps.Request(
                    environ={'HTTP_ACCEPT_LANGUAGE': header},
                    context=contexts.Context(),
                )
                self.assertEqual(
                    requests.parse_accept_language(request),
                    expect,
                )


if __name__ == '__main__':
    unittest.main()
