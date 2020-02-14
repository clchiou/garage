import unittest

from g1.asyncs import kernels
from g1.webs import consts
from g1.webs import wsgi_apps
from g1.webs.handlers import composers


class TestCaseBase(unittest.TestCase):

    ENVIRON = {
        'REQUEST_METHOD': 'GET',
        'PATH_INFO': '/foo/bar',
        'QUERY_STRING': '',
    }

    def setUp(self):
        super().setUp()
        self.request = None
        self.response = None
        self.handler = None
        self.calls = []

    def assert_response(self, status, headers):
        self.assertIs(self.response.status, status)
        self.assertEqual(self.response.headers, headers)

    def assert_http_error(self, exc, status, headers):
        self.assertIs(exc.status, status)
        self.assertEqual(exc.headers, headers)

    def set_request(self, **kwargs):
        environ = self.ENVIRON.copy()
        environ.update(**kwargs)
        self.request = wsgi_apps.Request(environ=environ)

    def make_noop_handler(self, name):

        async def noop(request, response):
            del request, response  # Unused.
            self.calls.append(name)

        return noop


class MethodRouterTest(TestCaseBase):

    def run_handler(self, method):
        self.set_request(REQUEST_METHOD=method)
        self.response = wsgi_apps._Response(None)
        self.calls.clear()
        kernels.run(
            self.handler(self.request, wsgi_apps.Response(self.response)),
            timeout=0.01,
        )

    @kernels.with_kernel
    def test_router(self):
        self.handler = composers.MethodRouter({
            consts.METHOD_HEAD:
            self.make_noop_handler('HEAD'),
            consts.METHOD_GET:
            self.make_noop_handler('GET'),
        })
        self.assertEqual(self.calls, [])

        self.run_handler(consts.METHOD_GET)
        self.assertEqual(self.calls, ['GET'])
        self.assert_response(consts.Statuses.OK, {})

        self.run_handler(consts.METHOD_HEAD)
        self.assertEqual(self.calls, ['HEAD'])
        self.assert_response(consts.Statuses.OK, {})

        self.run_handler(consts.METHOD_OPTIONS)
        self.assertEqual(self.calls, [])
        self.assert_response(
            consts.Statuses.NO_CONTENT,
            {consts.HEADER_ALLOW: 'GET, HEAD, OPTIONS'},
        )

        with self.assertRaisesRegex(
            wsgi_apps.HttpError,
            r'unsupported request method: PUT',
        ) as cm:
            self.run_handler(consts.METHOD_PUT)
        self.assertEqual(self.calls, [])
        self.assert_http_error(
            cm.exception,
            consts.Statuses.METHOD_NOT_ALLOWED,
            {consts.HEADER_ALLOW: 'GET, HEAD, OPTIONS'},
        )

    @kernels.with_kernel
    def test_no_auto_options(self):
        self.handler = composers.MethodRouter(
            {
                consts.METHOD_HEAD: self.make_noop_handler('HEAD'),
                consts.METHOD_GET: self.make_noop_handler('GET'),
            },
            auto_options=False,
        )
        with self.assertRaisesRegex(
            wsgi_apps.HttpError,
            r'unsupported request method: OPTIONS',
        ) as cm:
            self.run_handler(consts.METHOD_OPTIONS)
        self.assert_http_error(
            cm.exception,
            consts.Statuses.METHOD_NOT_ALLOWED,
            {consts.HEADER_ALLOW: 'GET, HEAD'},
        )

    @kernels.with_kernel
    def test_user_defined_options(self):
        self.handler = composers.MethodRouter({
            consts.METHOD_GET:
            self.make_noop_handler('GET'),
            consts.METHOD_OPTIONS:
            self.make_noop_handler('OPTIONS'),
        })
        self.assertEqual(self.calls, [])

        self.run_handler(consts.METHOD_OPTIONS)
        self.assertEqual(self.calls, ['OPTIONS'])
        self.assert_response(consts.Statuses.OK, {})

        with self.assertRaisesRegex(
            wsgi_apps.HttpError,
            r'unsupported request method: PUT',
        ) as cm:
            self.run_handler(consts.METHOD_PUT)
        self.assertEqual(self.calls, [])
        self.assert_http_error(
            cm.exception,
            consts.Statuses.METHOD_NOT_ALLOWED,
            {consts.HEADER_ALLOW: 'GET, OPTIONS'},
        )

    def test_invalid_args(self):
        with self.assertRaisesRegex(AssertionError, r'expect non-empty'):
            composers.MethodRouter({})


class PathPatternRouterTest(TestCaseBase):

    def run_handler(self, path):
        self.set_request(PATH_INFO=path)
        self.response = wsgi_apps._Response(None)
        self.calls.clear()
        kernels.run(
            self.handler(self.request, wsgi_apps.Response(self.response)),
            timeout=0.01,
        )

    @kernels.with_kernel
    def test_router(self):
        self.handler = composers.PathPatternRouter([
            (r'/a/p', self.make_noop_handler('/a/p')),
            (r'/a/q', self.make_noop_handler('/a/q')),
            (r'/a', self.make_noop_handler('/a')),
        ])
        self.set_request()
        self.assertEqual(self.request.context, {})
        self.assertIsNone(composers.PathPatternRouter.group(self.request))
        self.assertNotIn(composers.PATH_MATCH, self.request.context)
        self.assertEqual(
            composers.PathPatternRouter.get_path_str(self.request),
            '/foo/bar',
        )

        self.run_handler('/a/p/x')
        self.assertEqual(self.calls, ['/a/p'])
        self.assertEqual(set(self.request.context), {composers.PATH_MATCH})
        self.assertEqual(
            composers.PathPatternRouter.get_path_str(self.request),
            '/x',
        )
        self.assert_response(consts.Statuses.OK, {})

        self.run_handler('/a/q')
        self.assertEqual(self.calls, ['/a/q'])
        self.assertEqual(set(self.request.context), {composers.PATH_MATCH})
        self.assertEqual(
            composers.PathPatternRouter.get_path_str(self.request),
            '',
        )
        self.assert_response(consts.Statuses.OK, {})

        self.run_handler('/a/q/')
        self.assertEqual(self.calls, ['/a/q'])
        self.assertEqual(set(self.request.context), {composers.PATH_MATCH})
        self.assertEqual(
            composers.PathPatternRouter.get_path_str(self.request),
            '/',
        )
        self.assert_response(consts.Statuses.OK, {})

        self.run_handler('/a/r/foo/bar')
        self.assertEqual(self.calls, ['/a'])
        self.assertEqual(set(self.request.context), {composers.PATH_MATCH})
        self.assertEqual(
            composers.PathPatternRouter.get_path_str(self.request),
            '/r/foo/bar',
        )
        self.assert_response(consts.Statuses.OK, {})

        with self.assertRaisesRegex(
            wsgi_apps.HttpError,
            r'path does not match any pattern: ',
        ) as cm:
            self.run_handler('/foo/bar')
        self.assertEqual(self.calls, [])
        self.assert_http_error(cm.exception, consts.Statuses.NOT_FOUND, {})

        # You cannot override a PATH_MATCH entry in context.
        self.run_handler('/a/p/x')
        self.assertIn(composers.PATH_MATCH, self.request.context)
        with self.assertRaisesRegex(AssertionError, r'expect.*not containing'):
            kernels.run(
                self.handler(self.request, wsgi_apps.Response(self.response)),
                timeout=0.01,
            )

    @kernels.with_kernel
    def test_user_defined_named_groups(self):
        self.handler = composers.PathPatternRouter([
            (r'/(?P<d>\d+)-suffix', self.make_noop_handler('digits')),
            (r'/(?P<l>[a-z]+)xyz', self.make_noop_handler('letters')),
        ])

        self.run_handler('/012-suffix/spam/egg')
        self.assertEqual(self.calls, ['digits'])
        self.assertEqual(set(self.request.context), {composers.PATH_MATCH})
        self.assertEqual(
            composers.PathPatternRouter.get_path_str(self.request),
            '/spam/egg',
        )
        self.assertEqual(
            composers.PathPatternRouter.group(self.request), '/012-suffix'
        )
        self.assertEqual(
            composers.PathPatternRouter.group(self.request, 'd', 'l'),
            ('012', None),
        )
        self.assert_response(consts.Statuses.OK, {})

        self.run_handler('/abcxyz/spam/egg')
        self.assertEqual(self.calls, ['letters'])
        self.assertEqual(set(self.request.context), {composers.PATH_MATCH})
        self.assertEqual(
            composers.PathPatternRouter.get_path_str(self.request),
            '/spam/egg',
        )
        self.assertEqual(
            composers.PathPatternRouter.group(self.request), '/abcxyz'
        )
        self.assertEqual(
            composers.PathPatternRouter.group(self.request, 'd', 'l'),
            (None, 'abc'),
        )
        self.assert_response(consts.Statuses.OK, {})

    @kernels.with_kernel
    def test_user_defined_groups(self):
        # Although we test this usage, this usage is not recommended;
        # use named groups instead.
        self.handler = composers.PathPatternRouter([
            (r'/(\d+)-suffix', self.make_noop_handler('digits')),
            (r'/([a-z]+)-suffix', self.make_noop_handler('letters')),
        ])

        self.run_handler('/012-suffix/spam/egg')
        self.assertEqual(self.calls, ['digits'])
        self.assertEqual(set(self.request.context), {composers.PATH_MATCH})
        self.assertEqual(
            composers.PathPatternRouter.get_path_str(self.request),
            '/spam/egg',
        )
        self.assertEqual(
            composers.PathPatternRouter.group(self.request), '/012-suffix'
        )
        self.assertEqual(
            composers.PathPatternRouter.group(self.request, 0, 1, 2, 3, 4),
            ('/012-suffix', '/012-suffix', '012', None, None),
        )
        self.assert_response(consts.Statuses.OK, {})

    def test_invalid_args(self):
        with self.assertRaisesRegex(AssertionError, r'expect non-empty'):
            composers.PathPatternRouter([])


if __name__ == '__main__':
    unittest.main()
