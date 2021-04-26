import unittest

import contextlib
import io

from g1.bases import contexts
from g1.webs import consts
from g1.webs import wsgi_apps
from g1.webs.handlers import etags


class EtagsTest(unittest.TestCase):

    ENVIRON = {
        'REQUEST_METHOD': 'GET',
        'PATH_INFO': '/foo/bar',
        'QUERY_STRING': '',
    }

    @contextlib.contextmanager
    def assert_304(self, headers):
        with self.assertRaises(wsgi_apps.HttpError) as cm:
            yield
        self.assertIs(cm.exception.status, consts.Statuses.NOT_MODIFIED)
        self.assertEqual(cm.exception.headers, headers)

    def make_request(self, etags_str):
        environ = self.ENVIRON.copy()
        environ['HTTP_IF_NONE_MATCH'] = etags_str
        return wsgi_apps.Request(environ=environ, context=contexts.Context())

    @staticmethod
    def make_response(etag):
        response = wsgi_apps.Response(wsgi_apps._Response(None, False))
        response.headers[consts.HEADER_ETAG] = etag
        return response

    def test_compute_etag(self):
        for content, etag in [
            (b'', '"d41d8cd98f00b204e9800998ecf8427e"'),
            (b'hello world', '"5eb63bbbe01eeed093cb22bb8f5acdc3"'),
            (bytes(65536), '"fcd6bcb56c1689fcef28b57c22475bad"'),
        ]:
            with self.subTest((content, etag)):
                self.assertEqual(etags.compute_etag(content), etag)
                self.assertEqual(
                    etags.compute_etag_from_file(io.BytesIO(content)),
                    etag,
                )

    def test_maybe_raise_304(self):
        request = self.make_request('"0", "1", "2"')
        response = self.make_response('"1"')
        with self.assert_304({'ETag': '"1"'}):
            etags.maybe_raise_304(request, response)

    def test_maybe_raise_304_match_all(self):
        request = self.make_request('*')
        response = self.make_response('"1"')
        with self.assert_304({'ETag': '"1"'}):
            etags.maybe_raise_304(request, response)

    def test_maybe_raise_304_no_matching(self):
        request = self.make_request('"1"')
        response = self.make_response('"2"')
        etags.maybe_raise_304(request, response)

    def test_match_all(self):
        match_all = etags._MatchAll()
        self.assertIn('x', match_all)
        self.assertIn('y', match_all)

    def test_parse_etags(self):
        self.assertIsInstance(etags._parse_etags('  *  '), etags._MatchAll)
        self.assertEqual(etags._parse_etags('"1"'), {'"1"'})
        self.assertEqual(etags._parse_etags('"1"  ,  "2","1"'), {'"1"', '"2"'})
        self.assertEqual(
            etags._parse_etags('"3", "1", "4", "2", W/"99"'),
            {'"1"', '"2"', '"3"', '"4"', 'W/"99"'},
        )


if __name__ == '__main__':
    unittest.main()
