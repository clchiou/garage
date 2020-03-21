import unittest

from pathlib import Path

from g1.asyncs import kernels
from g1.bases import contexts
from g1.webs import consts
from g1.webs import wsgi_apps
from g1.webs.handlers import etags
from g1.webs.handlers import files


class FilesTest(unittest.TestCase):

    @staticmethod
    def make_request(path_str):
        return wsgi_apps.Request(
            environ={'PATH_INFO': path_str}, context=contexts.Context()
        )

    def test_get_local_path(self):
        dir_path = Path(__file__).parent.parent.resolve()
        self.assertEqual(
            files.get_local_path(
                self.make_request('//.//./tests/../tests/test_files.py'),
                dir_path,
            ),
            dir_path / 'tests/test_files.py',
        )
        with self.assertRaisesRegex(wsgi_apps.HttpError, r'out of scope: '):
            files.get_local_path(
                self.make_request('..'),
                dir_path,
            )
        with self.assertRaisesRegex(wsgi_apps.HttpError, r'not a file: '):
            files.get_local_path(
                self.make_request('tests'),
                dir_path,
            )

    def test_guess_content_type(self):
        for filename, expect in (
            ('foo.js', 'text/javascript'),
            ('foo.txt', 'text/plain'),
            ('foo.txt.tar', 'application/x-tar'),
            ('foo.txt.tar.gz', 'application/x-tar+gzip'),
        ):
            with self.subTest(filename):
                self.assertEqual(files.guess_content_type(filename), expect)


class HandlerTest(unittest.TestCase):

    DIR_PATH = Path(__file__).parent.parent.resolve()

    def setUp(self):
        super().setUp()
        self.request = None
        self.response = None
        self.handler = None

    def assert_request(self, context):
        self.assertEqual(self.request.context.asdict(), context)

    def assert_response(self, status, headers, content):
        self.assertIs(self.response.status, status)
        self.assertEqual(self.response.headers, headers)
        contents = []
        while True:
            data = self.response._content.read_nonblocking()
            if not data:
                break
            contents.append(data)
        self.assertEqual(b''.join(contents), content)

    def set_request(self, method, path_str):
        self.request = wsgi_apps.Request(
            environ={
                'REQUEST_METHOD': method,
                'PATH_INFO': path_str,
            },
            context=contexts.Context(),
        )

    def run_handler(self):
        self.response = wsgi_apps._Response(None)
        kernels.run(
            self.handler(self.request, wsgi_apps.Response(self.response)),
            timeout=0.01,
        )

    @kernels.with_kernel
    def test_all(self):
        self.handler = files.make_dir_handler(self.DIR_PATH)
        local_path = self.DIR_PATH / 'tests/test_files.py'
        response_headers = {
            consts.HEADER_CONTENT_TYPE: 'text/x-python',
            consts.HEADER_CONTENT_LENGTH: str(local_path.stat().st_size),
            consts.HEADER_ETAG: etags.compute_etag(local_path.read_bytes()),
        }

        self.set_request(consts.METHOD_OPTIONS, 'tests/test_files.py')
        self.run_handler()
        self.assert_request({files.LOCAL_PATH: local_path})
        self.assert_response(
            consts.Statuses.NO_CONTENT,
            {consts.HEADER_ALLOW: 'GET, HEAD, OPTIONS'},
            b'',
        )

        self.set_request(consts.METHOD_HEAD, 'tests/test_files.py')
        self.run_handler()
        self.assert_request({files.LOCAL_PATH: local_path})
        self.assert_response(consts.Statuses.OK, response_headers, b'')

        self.set_request(consts.METHOD_GET, 'tests/test_files.py')
        self.run_handler()
        self.assert_request({files.LOCAL_PATH: local_path})
        self.assert_response(
            consts.Statuses.OK, response_headers, local_path.read_bytes()
        )
        with self.assertRaisesRegex(AssertionError, r'expect.*not in'):
            self.run_handler()

        self.set_request(consts.METHOD_GET, '..')
        with self.assertRaisesRegex(wsgi_apps.HttpError, r'out of scope: '):
            self.run_handler()

        self.set_request(consts.METHOD_GET, 'tests')
        with self.assertRaisesRegex(wsgi_apps.HttpError, r'not a file: '):
            self.run_handler()

        self.set_request(consts.METHOD_PUT, 'tests/test_files.py')
        with self.assertRaisesRegex(
            wsgi_apps.HttpError,
            r'unsupported request method: PUT',
        ):
            self.run_handler()

    @kernels.with_kernel
    def test_path_checker(self):
        self.handler = files.DirHandler(self.DIR_PATH).check
        self.set_request(consts.METHOD_GET, 'tests/test_files.py')
        self.run_handler()
        self.assert_request({
            files.LOCAL_PATH:
            self.DIR_PATH / 'tests/test_files.py',
        })
        with self.assertRaisesRegex(AssertionError, r'expect.*not in'):
            self.run_handler()

        self.set_request(consts.METHOD_GET, '..')
        with self.assertRaisesRegex(wsgi_apps.HttpError, r'out of scope: '):
            self.run_handler()

        self.set_request(consts.METHOD_GET, 'tests')
        with self.assertRaisesRegex(wsgi_apps.HttpError, r'not a file: '):
            self.run_handler()

    @kernels.with_kernel
    def test_dir_handler(self):
        handler = files.DirHandler(self.DIR_PATH)
        local_path = self.DIR_PATH / 'tests/test_files.py'
        response_headers = {
            consts.HEADER_CONTENT_TYPE: 'text/x-python',
            consts.HEADER_CONTENT_LENGTH: str(local_path.stat().st_size),
            consts.HEADER_ETAG: etags.compute_etag(local_path.read_bytes()),
        }

        self.handler = handler.head
        self.set_request(consts.METHOD_HEAD, 'tests/test_files.py')
        self.run_handler()
        self.assert_request({})
        self.assert_response(consts.Statuses.OK, response_headers, b'')

        self.handler = handler.get
        self.set_request(consts.METHOD_GET, 'tests/test_files.py')
        self.run_handler()
        self.assert_request({})
        self.assert_response(
            consts.Statuses.OK, response_headers, local_path.read_bytes()
        )

        self.set_request(consts.METHOD_GET, '..')
        with self.assertRaisesRegex(wsgi_apps.HttpError, r'out of scope: '):
            self.run_handler()

        self.set_request(consts.METHOD_GET, 'tests')
        with self.assertRaisesRegex(wsgi_apps.HttpError, r'not a file: '):
            self.run_handler()

    @kernels.with_kernel
    def test_file_handler(self):
        local_path = self.DIR_PATH / 'tests/test_files.py'
        handler = files.FileHandler(local_path)
        response_headers = {
            consts.HEADER_CONTENT_TYPE: 'text/x-python',
            consts.HEADER_CONTENT_LENGTH: str(local_path.stat().st_size),
            consts.HEADER_ETAG: etags.compute_etag(local_path.read_bytes()),
        }

        self.handler = handler.head
        self.set_request(consts.METHOD_HEAD, 'tests/test_files.py')
        self.run_handler()
        self.assert_request({})
        self.assert_response(consts.Statuses.OK, response_headers, b'')

        self.handler = handler.get
        self.set_request(consts.METHOD_GET, 'tests/test_files.py')
        self.run_handler()
        self.assert_request({})
        self.assert_response(
            consts.Statuses.OK, response_headers, local_path.read_bytes()
        )


if __name__ == '__main__':
    unittest.main()
