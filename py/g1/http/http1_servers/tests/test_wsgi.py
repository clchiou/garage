import unittest
import unittest.mock

import http

from g1.asyncs import kernels
from g1.asyncs.bases import locks
from g1.asyncs.bases import queues
from g1.asyncs.bases import streams
from g1.asyncs.bases import tasks
from g1.http.http1_servers import wsgi


class HttpSessionTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.mock_sock = unittest.mock.Mock(spec_set=['recv', 'send'])
        self.mock_sock.recv = unittest.mock.AsyncMock()
        self.mock_sock.send = unittest.mock.AsyncMock()
        self.mock_sock.send.side_effect = self.mock_send

    def assert_send(self, *data_per_call):
        self.mock_sock.send.assert_has_calls([
            unittest.mock.call(data) for data in data_per_call
        ])

    @staticmethod
    async def mock_send(data):
        return len(data)

    @staticmethod
    async def get_body_chunks(context):
        chunks = []
        while True:
            chunk = await context.get_body_chunk()
            if not chunk:
                break
            chunks.append(chunk)
        return chunks

    @kernels.with_kernel
    def test_handle_request(self):
        http_500_keep_alive = (
            b'HTTP/1.1 500 Internal Server Error\r\n'
            b'Connection: keep-alive\r\n'
            b'\r\n',
        )
        http_500_not_keep_alive = (
            b'HTTP/1.1 500 Internal Server Error\r\n'
            b'Connection: close\r\n'
            b'\r\n',
        )

        session = wsgi.HttpSession(self.mock_sock, None, {})
        session._send_response = unittest.mock.AsyncMock()
        session._run_application = unittest.mock.AsyncMock()
        for (
            keep_alive,
            send_response,
            run_application,
            has_begun,
            expect_keep_alive,
            expect_send,
        ) in [
            (True, None, None, True, True, ()),
            (True, wsgi._SessionExit, None, True, False, ()),
            (True, None, wsgi._SessionExit, True, False, ()),
            (True, ValueError, None, True, False, ()),
            (True, None, ValueError, True, False, ()),
            (True, ValueError, None, False, True, http_500_keep_alive),
            (True, None, ValueError, False, True, http_500_keep_alive),
            # NOTE: If keep_alive is false, send_response cannot be
            # None.  This is the expected behavior of send_response, and
            # our mock has to respect that.
            (False, wsgi._SessionExit, None, True, False, ()),
            (False, wsgi._SessionExit, ValueError, True, False, ()),
            (False, ValueError, None, True, False, ()),
            (False, ValueError, None, False, False, http_500_not_keep_alive),
        ]:
            with self.subTest((
                keep_alive,
                send_response,
                run_application,
                has_begun,
                expect_keep_alive,
                expect_send,
            )):
                self.mock_sock.send.reset_mock()
                session._response_queue._has_begun = has_begun
                self.assertEqual(
                    session._response_queue.has_begun(), has_begun
                )
                session._send_response.side_effect = send_response
                session._run_application.side_effect = run_application

                if expect_keep_alive:
                    kernels.run(
                        session._handle_request({}, keep_alive),
                        timeout=0.01,
                    )
                else:
                    with self.assertRaises(wsgi._SessionExit):
                        kernels.run(
                            session._handle_request({}, keep_alive),
                            timeout=0.01,
                        )
                self.assert_send(*expect_send)

    @kernels.with_kernel
    def test_handle_request_100_continue(self):
        session = wsgi.HttpSession(self.mock_sock, None, {})
        for conn_header, keep_alive, expect_keep_alive in [
            ('Keep-Alive', True, True),
            ('Keep-Alive', False, True),
            ('close', True, False),
            ('close', False, False),
            (None, True, True),
            (None, False, False),
        ]:
            with self.subTest((conn_header, keep_alive, expect_keep_alive)):
                environ = {'HTTP_EXPECT': '100-Continue'}
                if conn_header is not None:
                    environ['HTTP_CONNECTION'] = conn_header
                if expect_keep_alive:
                    kernels.run(
                        session._handle_request(environ, keep_alive),
                        timeout=0.01,
                    )
                    self.assert_send(
                        b'HTTP/1.1 100 Continue\r\n'
                        b'Connection: keep-alive\r\n'
                        b'\r\n'
                    )
                else:
                    with self.assertRaises(wsgi._SessionExit):
                        kernels.run(
                            session._handle_request(environ, keep_alive),
                            timeout=0.01,
                        )
                    self.assert_send(
                        b'HTTP/1.1 100 Continue\r\n'
                        b'Connection: close\r\n'
                        b'\r\n'
                    )

    @kernels.with_kernel
    def test_run_application_aiter(self):

        class MockBody:

            def __init__(self):
                self._iter = iter([b'x', b'', b'', b'', b'y'])
                self.closed = False

            def __aiter__(self):
                return self

            async def __anext__(self):
                try:
                    return next(self._iter)
                except StopIteration:
                    raise StopAsyncIteration from None

            async def close(self):
                self.closed = True

        mock_body = MockBody()
        mock_app = unittest.mock.AsyncMock()
        mock_app.side_effect = [mock_body]

        session = wsgi.HttpSession(None, mock_app, {})
        context = wsgi._ApplicationContext()

        run_task = tasks.spawn(session._run_application(context, {}))
        get_task = tasks.spawn(self.get_body_chunks(context))

        kernels.run(timeout=0.01)

        self.assertTrue(mock_body.closed)
        self.assertTrue(context._chunks.is_closed())

        self.assertTrue(run_task.is_completed())
        run_task.get_result_nonblocking()

        self.assertTrue(get_task.is_completed())
        self.assertEqual(get_task.get_result_nonblocking(), [b'x', b'y'])

    @kernels.with_kernel
    def test_run_application_non_aiter(self):
        mock_app = unittest.mock.AsyncMock()
        mock_app.return_value = [b'x', b'', b'', b'', b'y']

        session = wsgi.HttpSession(None, mock_app, {})
        context = wsgi._ApplicationContext()

        run_task = tasks.spawn(session._run_application(context, {}))
        get_task = tasks.spawn(self.get_body_chunks(context))

        kernels.run(timeout=0.01)

        self.assertTrue(context._chunks.is_closed())

        self.assertTrue(run_task.is_completed())
        run_task.get_result_nonblocking()

        self.assertTrue(get_task.is_completed())
        self.assertEqual(get_task.get_result_nonblocking(), [b'x', b'y'])

    @kernels.with_kernel
    def test_send_response(self):

        def make_context(status, headers, *body_chunks):
            context = wsgi._ApplicationContext()
            context._status = status
            context._headers = headers
            context._chunks = queues.Queue()  # Unset capacity for test.
            for chunk in body_chunks:
                context._chunks.put_nonblocking(chunk)
            context.end_body_chunks()
            return context

        session = wsgi.HttpSession(self.mock_sock, None, {})
        for (
            context,
            keep_alive,
            expect_data_per_call,
            expect_not_session_exit,
        ) in [
            # header: none ; body: none ; omit_body: false
            (
                make_context(http.HTTPStatus.OK, []),
                True,
                [
                    b'HTTP/1.1 200 OK\r\n'
                    b'Connection: keep-alive\r\n'
                    b'Content-Length: 0\r\n'
                    b'\r\n',
                ],
                True,
            ),
            # header: custom ; body: one chunk ; omit_body: false
            (
                make_context(
                    http.HTTPStatus.NOT_FOUND, [(b'x', b'y')], b'foo bar'
                ),
                False,
                [
                    b'HTTP/1.1 404 Not Found\r\n'
                    b'x: y\r\n'
                    b'Connection: close\r\n'
                    b'Content-Length: 7\r\n'
                    b'\r\n',
                    b'foo bar',
                ],
                False,
            ),
            # header: connection ; body: multiple chunks ; omit_body: false
            (
                make_context(
                    http.HTTPStatus.OK,
                    [(b'connection', b'KeeP-Alive')],
                    b'spam',
                    b' ',
                    b'egg',
                ),
                False,
                [
                    b'HTTP/1.1 200 OK\r\n'
                    b'connection: KeeP-Alive\r\n'
                    b'Content-Length: 8\r\n'
                    b'\r\n',
                    b'spam',
                    b' ',
                    b'egg',
                ],
                True,
            ),
            # header: connection, content-length ; body: multiple chunks
            # omit_body: false
            (
                make_context(
                    http.HTTPStatus.OK,
                    [(b'Connection', b'close'), (b'cOnTeNt-LeNgTh', b'8')],
                    b'spam',
                    b' ',
                    b'egg',
                ),
                True,
                [
                    b'HTTP/1.1 200 OK\r\n'
                    b'Connection: close\r\n'
                    b'cOnTeNt-LeNgTh: 8\r\n'
                    b'\r\n',
                    b'spam',
                    b' ',
                    b'egg',
                ],
                False,
            ),
            # header: none ; body: multiple chunks
            # omit_body: true
            (
                make_context(
                    http.HTTPStatus.NOT_MODIFIED, [], b'x', b' ', b'y'
                ),
                True,
                [
                    b'HTTP/1.1 304 Not Modified\r\n'
                    b'Connection: keep-alive\r\n'
                    b'Content-Length: 3\r\n'
                    b'\r\n',
                ],
                True,
            ),
            # header: wrong content-length; body: multiple chunks
            # omit_body: false
            (
                make_context(
                    http.HTTPStatus.OK,
                    [(b'content-length', b'8')],
                    b'a',
                    b' ',
                    b'b',
                ),
                True,
                [
                    b'HTTP/1.1 200 OK\r\n'
                    b'content-length: 8\r\n'
                    b'Connection: keep-alive\r\n'
                    b'\r\n',
                    b'a',
                    b' ',
                    b'b',
                ],
                False,
            ),
        ]:
            with self.subTest((
                context,
                keep_alive,
                expect_data_per_call,
                expect_not_session_exit,
            )):
                self.mock_sock.send.reset_mock()

                send_task = tasks.spawn(
                    session._send_response(context, {}, keep_alive)
                )
                kernels.run(timeout=0.01)

                self.assertTrue(send_task.is_completed())
                if expect_not_session_exit:
                    send_task.get_result_nonblocking()
                else:
                    with self.assertRaises(wsgi._SessionExit):
                        send_task.get_result_nonblocking()

                self.assertTrue(context._is_committed)
                self.assertFalse(session._response_queue._has_begun)
                self.assertFalse(
                    session._response_queue._headers_sent.is_set()
                )
                self.assert_send(*expect_data_per_call)

    def test_should_omit_body(self):
        for status, environ, expect in [
            (http.HTTPStatus(100), {}, True),
            (http.HTTPStatus(101), {}, True),
            (http.HTTPStatus(102), {}, True),
            (http.HTTPStatus(204), {}, True),
            (http.HTTPStatus(205), {}, True),
            (http.HTTPStatus(304), {}, True),
            (
                http.HTTPStatus(200),
                {
                    'REQUEST_METHOD': 'HEAD',
                },
                True,
            ),
            (http.HTTPStatus(200), {}, False),
        ]:
            with self.subTest((status, environ, expect)):
                self.assertEqual(
                    wsgi.HttpSession._should_omit_body(status, environ),
                    expect,
                )

    @kernels.with_kernel
    def test_put_short_response_keep_alive(self):
        session = wsgi.HttpSession(self.mock_sock, None, {})
        kernels.run(
            session._put_short_response(http.HTTPStatus.OK, True),
            timeout=0.01,
        )
        self.assert_send(b'HTTP/1.1 200 OK\r\nConnection: keep-alive\r\n\r\n')

    @kernels.with_kernel
    def test_put_short_response_not_keep_alive(self):
        session = wsgi.HttpSession(self.mock_sock, None, {})
        kernels.run(
            session._put_short_response(http.HTTPStatus.OK, False),
            timeout=0.01,
        )
        self.assert_send(b'HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n')


class RequestQueueTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.mock_sock = unittest.mock.Mock(spec_set=['recv'])
        self.mock_sock.recv = unittest.mock.AsyncMock()
        self.request_queue = wsgi._RequestQueue(self.mock_sock, {})

    def get_request(self):
        environ = kernels.run(self.request_queue.get())
        if environ is None:
            return None, None
        return environ, environ.pop('wsgi.input').read_nonblocking()

    def parse_request_line(self, line):
        environ = {}
        self.request_queue._parse_request_line(line, environ)
        return environ

    def parse_request_header(self, line):
        return self.request_queue._parse_request_header(line)

    @kernels.with_kernel
    def test_get_request_one_byte_per_chunk(self):
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
            self.get_request(),
            (
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

        with self.assertRaisesRegex(
            wsgi._RequestError,
            r'invalid request line: \'some more data after the request\'',
        ):
            self.get_request()

        self.assertEqual(self.get_request(), (None, None))
        self.assertEqual(self.get_request(), (None, None))
        self.assertEqual(self.get_request(), (None, None))

    @kernels.with_kernel
    def test_get_request_eof(self):
        self.mock_sock.recv.return_value = b''
        self.assertEqual(self.get_request(), (None, None))
        self.assertEqual(self.get_request(), (None, None))
        self.assertEqual(self.get_request(), (None, None))

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
            wsgi._RequestError,
            r'invalid request line: ',
        ):
            self.parse_request_line('POST HTTP/1.1\r\n')
        with self.assertRaisesRegex(
            wsgi._RequestError,
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
            wsgi._RequestError,
            r'invalid request header: ',
        ):
            self.parse_request_header('foo\r\n')
        with self.assertRaisesRegex(
            wsgi._RequestError,
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
            wsgi._RequestError,
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

    def setUp(self):
        super().setUp()
        self.context = wsgi._ApplicationContext()

    def assert_context(self, is_committed, status, headers):
        self.assertEqual(self.context._is_committed, is_committed)
        self.assertEqual(self.context._status, status)
        self.assertEqual(self.context._headers, headers)

    def test_start_response(self):
        self.assert_context(False, None, [])

        self.context.start_response('200 OK', [('x', 'y')])
        self.assert_context(False, http.HTTPStatus.OK, [(b'x', b'y')])

        self.context.start_response('404 Not Found', [('p', 'q')])
        self.assert_context(False, http.HTTPStatus.NOT_FOUND, [(b'p', b'q')])

        self.context.commit()
        self.assert_context(True, http.HTTPStatus.NOT_FOUND, [(b'p', b'q')])

        with self.assertRaisesRegex(AssertionError, r'expect false'):
            self.context.start_response('200 OK', [('a', 'b')])

        self.assert_context(True, http.HTTPStatus.NOT_FOUND, [(b'p', b'q')])

    def test_start_response_exc_info(self):
        self.assert_context(False, None, [])

        self.context.start_response(
            '200 OK', [('x', 'y')], (ValueError, '', None)
        )
        self.assert_context(False, http.HTTPStatus.OK, [(b'x', b'y')])

        self.context.start_response(
            '404 Not Found', [('p', 'q')], (KeyError, '', None)
        )
        self.assert_context(False, http.HTTPStatus.NOT_FOUND, [(b'p', b'q')])

        self.context.commit()
        self.assert_context(True, http.HTTPStatus.NOT_FOUND, [(b'p', b'q')])

        with self.assertRaisesRegex(TypeError, r'foo bar'):
            self.context.start_response(
                '200 OK', [('a', 'b')], (TypeError, 'foo bar', None)
            )

        self.assert_context(True, http.HTTPStatus.NOT_FOUND, [(b'p', b'q')])

    def test_status_and_headers(self):
        self.assert_context(False, None, [])

        with self.assertRaisesRegex(AssertionError, r'expect true'):
            self.context.status  # pylint: disable=pointless-statement
        with self.assertRaisesRegex(AssertionError, r'expect true'):
            self.context.headers  # pylint: disable=pointless-statement

        self.context.start_response(
            '200 OK', [('x', 'y')], (ValueError, '', None)
        )
        self.assert_context(False, http.HTTPStatus.OK, [(b'x', b'y')])

        with self.assertRaisesRegex(AssertionError, r'expect true'):
            self.context.status  # pylint: disable=pointless-statement
        with self.assertRaisesRegex(AssertionError, r'expect true'):
            self.context.headers  # pylint: disable=pointless-statement

        self.context.commit()
        self.assert_context(True, http.HTTPStatus.OK, [(b'x', b'y')])

        self.assertEqual(self.context.status, http.HTTPStatus.OK)
        self.assertEqual(self.context.headers, [(b'x', b'y')])

    @kernels.with_kernel
    def test_body_chunks(self):

        chunks = []

        async def get_body_chunks():
            while True:
                chunk = await self.context.get_body_chunk()
                if not chunk:
                    break
                chunks.append(chunk)

        async def put_body_chunks():
            await self.context.put_body_chunk(b'a')
            await self.context.put_body_chunk(b'')
            await self.context.put_body_chunk(b'b')
            await self.context.put_body_chunk(b'')
            await self.context.put_body_chunk(b'c')

        put_task = tasks.spawn(put_body_chunks())
        with self.assertRaises(kernels.KernelTimeout):
            kernels.run(timeout=0.01)
        self.assertEqual(chunks, [])
        self.assertFalse(put_task.is_completed())

        get_task = tasks.spawn(get_body_chunks())
        with self.assertRaises(kernels.KernelTimeout):
            kernels.run(timeout=0.01)
        self.assertEqual(chunks, [b'a', b'b', b'c'])
        self.assertTrue(put_task.is_completed())
        self.assertFalse(get_task.is_completed())

        self.context.end_body_chunks()
        kernels.run(timeout=0.01)
        self.assertEqual(chunks, [b'a', b'b', b'c'])
        self.assertTrue(put_task.is_completed())
        self.assertTrue(get_task.is_completed())

        put_task.get_result_nonblocking()
        get_task.get_result_nonblocking()


class ResponseQueueTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.mock_sock = unittest.mock.Mock(spec_set=['send'])
        self.mock_sock.send = unittest.mock.AsyncMock()
        self.mock_sock.send.return_value = 1
        self.response_queue = wsgi._ResponseQueue(self.mock_sock)

    def assert_begin(self, expect):
        self.assertEqual(self.response_queue.has_begun(), expect)
        self.assertEqual(self.response_queue._has_begun, expect)
        self.assertEqual(self.response_queue._headers_sent.is_set(), expect)

    def assert_send_all(self, *data_per_call):
        self.mock_sock.send.assert_has_calls([
            unittest.mock.call(data[n:])
            for data in data_per_call
            for n in range(len(data))
        ])

    @kernels.with_kernel
    def test_begin(self):
        self.assert_begin(False)

        kernels.run(
            self.response_queue.begin(http.HTTPStatus.OK, [(b'x', b'y')]),
            timeout=0.01,
        )
        self.assert_begin(True)
        self.assert_send_all(b'HTTP/1.1 200 OK\r\nx: y\r\n\r\n')

        with self.assertRaisesRegex(AssertionError, r'expect false'):
            kernels.run(
                self.response_queue.begin(http.HTTPStatus.OK, []),
                timeout=0.01,
            )

    @kernels.with_kernel
    def test_put_body_chunk(self):
        self.assert_begin(False)
        with self.assertRaisesRegex(AssertionError, r'expect true'):
            kernels.run(
                self.response_queue.put_body_chunk(b'foo'),
                timeout=0.01,
            )

        self.assert_begin(False)
        kernels.run(
            self.response_queue.begin(http.HTTPStatus.OK, []),
            timeout=0.01,
        )
        self.assert_begin(True)

        kernels.run(
            self.response_queue.put_body_chunk(b''),
            timeout=0.01,
        )
        kernels.run(
            self.response_queue.put_body_chunk(b'bar'),
            timeout=0.01,
        )
        kernels.run(
            self.response_queue.put_body_chunk(b''),
            timeout=0.01,
        )
        self.assert_begin(True)

        self.assert_send_all(b'HTTP/1.1 200 OK\r\n\r\n', b'bar')

    @kernels.with_kernel
    def test_headers_sent_blocking(self):

        def assert_begin_but_not_sent():
            self.assertEqual(self.response_queue.has_begun(), True)
            self.assertEqual(self.response_queue._has_begun, True)
            self.assertEqual(self.response_queue._headers_sent.is_set(), False)

        block_send = locks.Event()

        async def mock_send(data):
            del data  # Unused.
            await block_send.wait()
            return 1

        self.mock_sock.send.side_effect = mock_send

        begin_task = tasks.spawn(
            self.response_queue.begin(http.HTTPStatus.OK, [])
        )
        with self.assertRaises(kernels.KernelTimeout):
            kernels.run(timeout=0.01)
        assert_begin_but_not_sent()
        self.assertFalse(begin_task.is_completed())

        put_task = tasks.spawn(self.response_queue.put_body_chunk(b'xyz'))
        with self.assertRaises(kernels.KernelTimeout):
            kernels.run(timeout=0.01)
        assert_begin_but_not_sent()
        self.assertFalse(begin_task.is_completed())
        self.assertFalse(put_task.is_completed())

        block_send.set()

        kernels.run(timeout=0.01)
        self.assert_begin(True)
        self.assertTrue(begin_task.is_completed())
        self.assertTrue(put_task.is_completed())
        begin_task.get_result_nonblocking()
        put_task.get_result_nonblocking()

        self.assert_send_all(b'HTTP/1.1 200 OK\r\n\r\n', b'xyz')

    @kernels.with_kernel
    def test_end(self):
        self.assert_begin(False)
        with self.assertRaisesRegex(AssertionError, r'expect true'):
            self.response_queue.end()

        self.assert_begin(False)
        kernels.run(
            self.response_queue.begin(http.HTTPStatus.NOT_FOUND, []),
            timeout=0.01,
        )
        self.assert_begin(True)

        self.response_queue.end()
        self.assert_begin(False)

        self.assert_send_all(b'HTTP/1.1 404 Not Found\r\n\r\n')


if __name__ == '__main__':
    unittest.main()
