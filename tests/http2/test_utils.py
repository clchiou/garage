import unittest

import contextlib
import filecmp
import http.server
import io
import os
import pathlib
import socket
import socketserver
import sys
import tempfile
import threading
from concurrent import futures

from garage.http2 import clients
from garage.http2 import utils

from tests.http2.mocks import *


class DownloadTest(unittest.TestCase):

    def setUp(self):
        # XXX: Work around TIME_WAIT state of connected sockets.
        socketserver.TCPServer.allow_reuse_address = True

    def tearDown(self):
        socketserver.TCPServer.allow_reuse_address = False

    def test_download_basic(self):
        requests_to_filename = [
            (
                [
                    'http://localhost:8000/file1-not',
                    'http://localhost:8000/file1',
                ],
                'file1',
            ),
        ]

        data_dirpath = pathlib.Path(__file__).with_name('data')
        if not data_dirpath.is_absolute():
            data_dirpath = pathlib.Path.cwd() / data_dirpath

        with contextlib.ExitStack() as stack:
            stderr, target = stack.enter_context(
                _redirect_stderr(io.StringIO()))
            try:
                stack.enter_context(_chdir(str(data_dirpath)))
                stack.enter_context(_start_server())
                root_dirpath = pathlib.Path(stack.enter_context(
                    tempfile.TemporaryDirectory()))

                print('data_dirpath', data_dirpath, file=sys.stderr)
                print('root_dirpath', root_dirpath, file=sys.stderr)

                with futures.ThreadPoolExecutor(1) as executor:
                    utils.download(
                        client=clients.Client(),
                        executor=executor,
                        requests_to_filename=requests_to_filename,
                        output_dirpath=(root_dirpath / 'test'),
                    )

                self.assertTrue(root_dirpath.is_dir())
                file1_path = root_dirpath / 'test' / 'file1'
                self.assertTrue(file1_path.is_file())
                self.assertTrue(filecmp.cmp(
                    str(data_dirpath / 'file1'),
                    str(file1_path),
                    shallow=False,
                ))
            except BaseException:
                print(target.getvalue(), file=stderr)
                raise


class FormTest(unittest.TestCase):

    def test_form(self):
        req_to_rep = {
            ('GET', 'http://uri_1/'): (
                200, b'<form action="http://uri_1"></form>'
            ),
            ('POST', 'http://uri_1/'): (200, 'hello world'),
            ('GET', 'http://uri_2/'): (200, b'<form></form><form></form>'),
            ('GET', 'http://uri_3/'): (
                200, b'''<form action="http://uri_3">
                         <input name="k1" value="v1"/>
                         <input name="k2" value="other_v2"/>
                         </form>
                      '''
            ),
            ('POST', 'http://uri_3/'): (200, 'form filled'),
        }
        session = MockSession(req_to_rep)
        client = clients.Client(_session=session, _sleep=fake_sleep)

        rep = utils.form(client, 'http://uri_1')
        self.assertEqual('hello world', rep.content)

        with self.assertRaisesRegex(ValueError, 'require one form'):
            rep = utils.form(client, 'http://uri_2')

        session._logs.clear()
        rep = utils.form(client, 'http://uri_3', form_data={'k2': 'v2'})
        self.assertEqual('form filled', rep.content)
        self.assertEqual(2, len(session._logs))
        self.assertEqual('GET', session._logs[0].method)
        self.assertEqual('http://uri_3/', session._logs[0].url)
        self.assertEqual('POST', session._logs[1].method)
        self.assertEqual('http://uri_3/', session._logs[1].url)
        self.assertListEqual(
            ['k1=v1', 'k2=v2'], sorted(session._logs[1].body.split('&')))


@contextlib.contextmanager
def _chdir(path):
    cwd = os.getcwd()
    os.chdir(path)
    try:
        yield path
    finally:
        os.chdir(cwd)


@contextlib.contextmanager
def _redirect_stderr(target):
    stderr = sys.stderr
    sys.stderr = target
    try:
        yield stderr, target
    finally:
        sys.stderr = stderr


@contextlib.contextmanager
def _start_server():
    httpd = socketserver.TCPServer(
        ('127.0.0.1', 8000), http.server.SimpleHTTPRequestHandler,
    )
    thread = threading.Thread(name='httpd', target=httpd.serve_forever)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


if __name__ == '__main__':
    unittest.main()
