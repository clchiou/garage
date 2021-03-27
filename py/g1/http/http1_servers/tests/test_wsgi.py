import unittest
import unittest.mock

import http

from g1.asyncs import kernels
from g1.asyncs.bases import streams
from g1.http.http1_servers import wsgi


class RequestParserTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.mock_sock = unittest.mock.Mock(spec_set=['recv'])
        self.mock_sock.recv = unittest.mock.AsyncMock()
        self.request_parser = wsgi._RequestParser(self.mock_sock)

    def next_request(self):
        environ = {}
        more = kernels.run(self.request_parser.next_request(environ))
        return (
            more,
            environ,
            environ.pop('wsgi.input').read_nonblocking() if more else None,
        )

    def parse_request_line(self, line):
        environ = {}
        self.request_parser._parse_request_line(line, environ)
        return environ

    def parse_request_header(self, line):
        return self.request_parser._parse_request_header(line)

    @kernels.with_kernel
    def test_next_request_one_byte_per_chunk(self):
        data = (
            b'GET /foo/bar?x=y HTTP/1.1\r\n'
            b'Host: localhost\r\n'
            b'Foo-Bar  :  X  \r\n'
            b'Content-Length: 11\r\n'
            b'Foo-Bar  :  Y  \r\n'
            b'\r\n'
            b'hello world'
            b'some more data after the request'
        )
        self.mock_sock.recv.side_effect = (
            [data[i:i + 1] for i in range(len(data))] + [b'']
        )
        self.assertEqual(
            self.next_request(),
            (
                True,
                {
                    'REQUEST_METHOD': 'GET',
                    'PATH_INFO': '/foo/bar',
                    'QUERY_STRING': 'x=y',
                    'HTTP_HOST': 'localhost',
                    'HTTP_FOO_BAR': 'X,Y',
                    'CONTENT_LENGTH': '11',
                },
                b'hello world',
            ),
        )

    @kernels.with_kernel
    def test_next_request_eof(self):
        self.mock_sock.recv.return_value = b''
        self.assertEqual(self.next_request(), (False, {}, None))

    def test_parse_request_line(self):
        self.assertEqual(
            self.parse_request_line('POST /foo/bar?x=y&p=q HTTP/1.1\r\n'),
            {
                'REQUEST_METHOD': 'POST',
                'PATH_INFO': '/foo/bar',
                'QUERY_STRING': 'x=y&p=q',
            },
        )
        self.assertEqual(
            self.parse_request_line('  gEt  XyZ  HtTp/999  \n'),
            {
                'REQUEST_METHOD': 'GET',
                'PATH_INFO': 'XyZ',
                'QUERY_STRING': '',
            },
        )
        with self.assertRaisesRegex(
            wsgi._RequestParserError,
            r'invalid request line: ',
        ):
            self.parse_request_line('POST HTTP/1.1\r\n')
        with self.assertRaisesRegex(
            wsgi._RequestParserError,
            r'invalid request line: ',
        ):
            self.parse_request_line('POST /path HTTP/1.1')

    def test_parse_request_header(self):
        self.assertEqual(
            self.parse_request_header('Content-Length: 101\r\n'),
            ('CONTENT_LENGTH', '101'),
        )
        self.assertEqual(
            self.parse_request_header('  Content-Type  :  text/plain  \n'),
            ('CONTENT_TYPE', 'text/plain'),
        )
        self.assertEqual(
            self.parse_request_header('  FoO-bAr  :  a b c d  \n'),
            ('HTTP_FOO_BAR', 'a b c d'),
        )
        self.assertEqual(
            self.parse_request_header(':path: /x/y/z\r\n'),
            (None, None),
        )
        with self.assertRaisesRegex(
            wsgi._RequestParserError,
            r'invalid request header: ',
        ):
            self.parse_request_header('foo\r\n')
        with self.assertRaisesRegex(
            wsgi._RequestParserError,
            r'invalid request header: ',
        ):
            self.parse_request_header('foo: bar')


class RequestBufferTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.mock_sock = unittest.mock.Mock(spec_set=['recv'])
        self.mock_sock.recv = unittest.mock.AsyncMock()
        self.request_buffer = wsgi._RequestBuffer(self.mock_sock)

    def assert_buffer(self, buffer, ended):
        self.assertEqual(self.request_buffer._buffer, buffer)
        self.assertEqual(self.request_buffer._size, sum(map(len, buffer)))
        self.assertEqual(self.request_buffer._ended, ended)

    def readline_decoded(self, limit=65536):
        return kernels.run(self.request_buffer.readline_decoded(limit))

    def read_into(self, size):
        stream = streams.BytesStream()
        kernels.run(self.request_buffer.read_into(stream, size))
        stream.close()
        return stream.read_nonblocking()

    @kernels.with_kernel
    def test_readline_decoded_eof(self):
        self.mock_sock.recv.return_value = b''
        self.assert_buffer([], False)
        self.assertEqual(self.readline_decoded(), '')
        self.assert_buffer([], True)

    @kernels.with_kernel
    def test_readline_decoded_one_byte_per_chunk(self):
        data = b'hello\nworld\r\n\n\n\r\n\nfoobar'
        self.mock_sock.recv.side_effect = (
            [data[i:i + 1] for i in range(len(data))] + [b'']
        )
        self.assert_buffer([], False)

        self.assertEqual(self.readline_decoded(), 'hello\n')
        self.assert_buffer([], False)

        self.assertEqual(self.readline_decoded(), 'world\r\n')
        self.assert_buffer([], False)

        self.assertEqual(self.readline_decoded(), '\n')
        self.assert_buffer([], False)

        self.assertEqual(self.readline_decoded(), '\n')
        self.assert_buffer([], False)

        self.assertEqual(self.readline_decoded(), '\r\n')
        self.assert_buffer([], False)

        self.assertEqual(self.readline_decoded(), '\n')
        self.assert_buffer([], False)

        self.assertEqual(self.readline_decoded(), 'foobar')
        self.assert_buffer([], True)

        self.assertEqual(self.readline_decoded(), '')
        self.assert_buffer([], True)

        self.assertEqual(len(self.mock_sock.recv.mock_calls), len(data) + 1)

    @kernels.with_kernel
    def test_readline_decoded_one_chunk(self):
        data = b'hello\nworld\r\n\n\n\r\n\nfoobar'
        self.mock_sock.recv.side_effect = [data, b'']
        self.assert_buffer([], False)

        self.assertEqual(self.readline_decoded(), 'hello\n')
        self.assert_buffer([b'world\r\n\n\n\r\n\nfoobar'], False)

        self.assertEqual(self.readline_decoded(), 'world\r\n')
        self.assert_buffer([b'\n\n\r\n\nfoobar'], False)

        self.assertEqual(self.readline_decoded(), '\n')
        self.assert_buffer([b'\n\r\n\nfoobar'], False)

        self.assertEqual(self.readline_decoded(), '\n')
        self.assert_buffer([b'\r\n\nfoobar'], False)

        self.assertEqual(self.readline_decoded(), '\r\n')
        self.assert_buffer([b'\nfoobar'], False)

        self.assertEqual(self.readline_decoded(), '\n')
        self.assert_buffer([b'foobar'], False)

        self.assertEqual(self.readline_decoded(), 'foobar')
        self.assert_buffer([], True)

        self.assertEqual(self.readline_decoded(), '')
        self.assert_buffer([], True)

        self.assertEqual(len(self.mock_sock.recv.mock_calls), 2)

    @kernels.with_kernel
    def test_readline_decoded_exceed_limit(self):
        data = b'0123456789abcdef'
        self.mock_sock.recv.side_effect = [data, b'']
        self.assert_buffer([], False)
        with self.assertRaisesRegex(
            wsgi._RequestParserError,
            r'request line length exceeds 15',
        ):
            self.readline_decoded(15)
        self.assert_buffer([b'0123456789abcdef'], False)
        self.assertEqual(len(self.mock_sock.recv.mock_calls), 1)

    @kernels.with_kernel
    def test_read_into_one_byte_per_chunk(self):
        data = b'hello\nworld\r\n\n\n\r\n\nfoobar'
        self.mock_sock.recv.side_effect = (
            [data[i:i + 1] for i in range(len(data))] + [b'']
        )
        self.assert_buffer([], False)

        self.assertEqual(self.read_into(3), b'hel')
        self.assert_buffer([], False)

        self.assertEqual(self.read_into(1), b'l')
        self.assert_buffer([], False)

        self.assertEqual(self.read_into(4), b'o\nwo')
        self.assert_buffer([], False)

        self.assertEqual(self.read_into(999), b'rld\r\n\n\n\r\n\nfoobar')
        self.assert_buffer([], True)

        self.assertEqual(self.read_into(1), b'')
        self.assert_buffer([], True)

        self.assertEqual(len(self.mock_sock.recv.mock_calls), len(data) + 1)

    @kernels.with_kernel
    def test_read_into_one_chunk(self):
        data = b'hello\nworld\r\n\n\n\r\n\nfoobar'
        self.mock_sock.recv.side_effect = [data, b'']
        self.assert_buffer([], False)

        self.assertEqual(self.readline_decoded(), 'hello\n')
        self.assert_buffer([b'world\r\n\n\n\r\n\nfoobar'], False)

        self.assertEqual(self.read_into(8), b'world\r\n\n')
        self.assert_buffer([b'\n\r\n\nfoobar'], False)

        self.assertEqual(self.read_into(11), b'\n\r\n\nfoobar')
        self.assert_buffer([], True)

        self.assertEqual(self.read_into(1), b'')
        self.assert_buffer([], True)

        self.assertEqual(len(self.mock_sock.recv.mock_calls), 2)


class ApplicationContextTest(unittest.TestCase):

    def test_app_ctx(self):
        app_ctx = wsgi._ApplicationContext()
        self.assertIsNone(app_ctx.status)
        self.assertEqual(app_ctx.headers, [])
        self.assertEqual(app_ctx.get_body(), b'')

        self.assertEqual(
            app_ctx.start_response(
                '200 OK',
                [('Content-Type', 'text/plain')],
            ),
            app_ctx.write,
        )
        self.assertIs(app_ctx.status, http.HTTPStatus.OK)
        self.assertEqual(app_ctx.headers, [(b'Content-Type', b'text/plain')])
        self.assertEqual(app_ctx.get_body(), b'')

        app_ctx.write(b'hello world')
        self.assertEqual(app_ctx.get_body(), b'hello world')

        self.assertEqual(
            app_ctx.start_response(
                '302 Found',
                [('XYZ', 'ABC')],
            ),
            app_ctx.write,
        )
        self.assertIs(app_ctx.status, http.HTTPStatus.FOUND)
        self.assertEqual(app_ctx.headers, [(b'XYZ', b'ABC')])
        self.assertEqual(app_ctx.get_body(), b'hello world')

        self.assertEqual(
            app_ctx.start_response(
                '404 Not Found',
                [('Foo-Bar', 'spam egg')],
                exc_info=True,
            ),
            app_ctx.write,
        )
        self.assertIs(app_ctx.status, http.HTTPStatus.NOT_FOUND)
        self.assertEqual(app_ctx.headers, [(b'Foo-Bar', b'spam egg')])
        self.assertEqual(app_ctx.get_body(), b'')


if __name__ == '__main__':
    unittest.main()
