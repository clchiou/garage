import unittest
import unittest.mock

from g1.asyncs import kernels
from g1.asyncs.bases import locks
from g1.asyncs.bases import tasks

import g1.webs
from g1.webs import consts
from g1.webs import wsgi_apps


class ExportTest(unittest.TestCase):

    def test_export_names(self):
        self.assertNotIn('consts', g1.webs.__all__)
        self.assertNotIn('wsgi_apps', g1.webs.__all__)
        s1 = set(consts.__all__)
        s2 = set(wsgi_apps.__all__)
        self.assertFalse(s1 & s2)


class ResponseTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.start_application_mock = unittest.mock.Mock()
        self.response = wsgi_apps._Response(self.start_application_mock)

    def assert_headers(self, headers):
        self.assertEqual(self.response.headers, headers)
        self.assertEqual(sorted(self.response.headers), sorted(headers))
        self.assertEqual(bool(self.response.headers), bool(headers))
        self.assertEqual(len(self.response.headers), len(headers))
        for key in headers:
            with self.subTest(key):
                self.assertIn(key, self.response.headers)
                self.assertEqual(self.response.headers[key], headers[key])
        self.assertNotIn('no-such-key', self.response.headers)

    def test_status(self):
        self.assertIs(self.response.status, consts.Statuses.OK)

        self.response.status = 400
        self.assertIs(self.response.status, consts.Statuses.BAD_REQUEST)

        self.response.commit()
        self.assertIs(self.response.status, consts.Statuses.BAD_REQUEST)

        with self.assertRaisesRegex(AssertionError, r'expect false-value'):
            self.response.status = 404
        self.assertIs(self.response.status, consts.Statuses.BAD_REQUEST)

    def test_headers(self):
        self.assert_headers({})

        self.response.headers['p'] = 'q'
        self.response.headers['r'] = 's'
        self.assert_headers({'p': 'q', 'r': 's'})

        del self.response.headers['r']
        self.assert_headers({'p': 'q'})

        self.response.commit()
        self.assert_headers({'p': 'q'})

        with self.assertRaisesRegex(AssertionError, r'expect false-value'):
            self.response.headers['x'] = 'y'
        with self.assertRaisesRegex(AssertionError, r'expect false-value'):
            del self.response.headers['x']
        self.assert_headers({'p': 'q'})

    def test_reset(self):
        self.response.status = 400
        self.response.headers['p'] = 'q'
        self.response.write_nonblocking(b'hello world')
        self.response.reset()
        self.assertIs(self.response.status, consts.Statuses.OK)
        self.assert_headers({})
        self.assertIsNone(self.response._content.read_nonblocking())

        self.response.commit()
        with self.assertRaisesRegex(AssertionError, r'expect false-value'):
            self.response.reset()

    @kernels.with_kernel
    def test_commit(self):
        self.assertFalse(self.response.is_committed())
        self.start_application_mock.assert_not_called()
        wait_task = tasks.spawn(self.response.wait_committed)
        with self.assertRaises(kernels.KernelTimeout):
            kernels.run(timeout=0.01)

        with self.assertRaisesRegex(AssertionError, r'expect true-value'):
            kernels.run(self.response.read, timeout=0.01)
        with self.assertRaisesRegex(AssertionError, r'expect true-value'):
            self.response.set_error_after_commit(None)

        self.response.commit()
        self.assertTrue(self.response.is_committed())
        self.start_application_mock.assert_called_once_with('200 OK', [])
        kernels.run(timeout=0.01)
        self.assertTrue(wait_task.is_completed())
        self.assertIsNone(wait_task.get_result_nonblocking())

        self.response.write_nonblocking(b'hello world')
        self.assertEqual(
            kernels.run(self.response.read, timeout=0.01),
            b'hello world',
        )

        # Repeated calls to commit has no effect.
        self.start_application_mock.reset_mock()
        self.response.commit()
        self.start_application_mock.assert_not_called()


class ApplicationTest(unittest.TestCase):

    ENVIRON = {
        'REQUEST_METHOD': 'GET',
        'PATH_INFO': '/',
        'QUERY_STRING': '',
    }

    def setUp(self):
        super().setUp()
        self.start_application_mock = unittest.mock.Mock()

    async def run_handler(self, handler):
        app = wsgi_apps.Application(handler)
        content = []
        try:
            async for data in await app(
                self.ENVIRON, self.start_application_mock
            ):
                content.append(data)
        finally:
            app.shutdown()
            await app.serve()
        if not content:
            return None
        else:
            return b''.join(content)

    @kernels.with_kernel
    def test_success(self):

        async def handler(request, response):
            del request
            response.headers['Content-Type'] = 'text/plain'
            await response.write(b'hello world')

        self.assertEqual(
            kernels.run(self.run_handler(handler), timeout=0.01),
            b'hello world',
        )
        self.start_application_mock.assert_called_once_with(
            '200 OK',
            [('Content-Type', 'text/plain')],
        )

    @kernels.with_kernel
    def test_redirect(self):

        async def handler(request, response):
            del request
            response.headers['Content-Type'] = 'text/plain'
            await response.write(b'hello world')
            raise wsgi_apps.HttpError.redirect(300, 'nothing', 'some-url')

        self.assertIsNone(kernels.run(self.run_handler(handler), timeout=0.01))
        self.start_application_mock.assert_called_once_with(
            '300 Multiple Choices',
            [('Location', 'some-url')],
        )

    @kernels.with_kernel
    def test_http_error(self):

        async def handler(request, response):
            del request
            response.headers['Content-Type'] = 'text/plain'
            await response.write(b'hello world')
            raise wsgi_apps.HttpError(400, 'nothing', content=b'some error')

        self.assertEqual(
            kernels.run(self.run_handler(handler), timeout=0.01),
            b'some error',
        )
        self.start_application_mock.assert_called_once_with(
            '400 Bad Request',
            [],
        )

    @kernels.with_kernel
    def test_error(self):

        async def handler(request, response):
            del request
            response.headers['Content-Type'] = 'text/plain'
            await response.write(b'hello world')
            raise Exception

        self.assertIsNone(kernels.run(self.run_handler(handler), timeout=0.01))
        self.start_application_mock.assert_called_once_with(
            '500 Internal Server Error',
            [],
        )

    @kernels.with_kernel
    def test_crash_after_commit(self):

        class Error(Exception):
            pass

        async def handler(request, response):
            del request
            response.headers['Content-Type'] = 'text/plain'
            response.commit()
            await response.write(b'hello world')
            raise Error

        with self.assertRaises(Error):
            kernels.run(self.run_handler(handler), timeout=0.01)
        # This is called before the crash.
        self.start_application_mock.assert_called_once_with(
            '200 OK',
            [('Content-Type', 'text/plain')],
        )

    @kernels.with_kernel
    def test_linger_on(self):

        quit_handler = locks.Event()
        handler_completed = locks.Event()

        async def handler(request, response):
            del request
            response.headers['Content-Type'] = 'text/plain'
            await response.write(b'hello world')
            response.close()
            await quit_handler.wait()
            handler_completed.set()

        async def get_content(content_iterator):
            content = []
            async for data in content_iterator:
                content.append(data)
            if not content:
                return None
            else:
                return b''.join(content)

        app = wsgi_apps.Application(handler)
        app_task = tasks.spawn(app(self.ENVIRON, self.start_application_mock))
        with self.assertRaises(kernels.KernelTimeout):
            kernels.run(timeout=0.01)
        self.assertTrue(app_task.is_completed())
        self.assertFalse(handler_completed.is_set())

        self.start_application_mock.assert_called_once_with(
            '200 OK',
            [('Content-Type', 'text/plain')],
        )
        self.assertEqual(
            kernels.run(
                get_content(app_task.get_result_nonblocking()),
                timeout=0.01,
            ),
            b'hello world',
        )
        # Handler lingers on after application completes.
        self.assertFalse(handler_completed.is_set())

        quit_handler.set()
        kernels.run(timeout=0.01)
        self.assertTrue(handler_completed.is_set())

        app.shutdown()
        kernels.run(app.serve(), timeout=0.01)


if __name__ == '__main__':
    unittest.main()
