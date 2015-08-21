import unittest

import contextlib
import filecmp
import pathlib
import socketserver
import sys
import tempfile
from concurrent import futures

from garage.http import clients
from garage.http import utils

from tests.http.mocks import *
from tests.http.server import *

try:
    import lxml.etree
except ImportError:
    skip_dom_parsing = True
else:
    skip_dom_parsing = False


class DownloadTest(unittest.TestCase):

    data_dirpath = pathlib.Path(__file__).with_name('data')
    if not data_dirpath.is_absolute():
        data_dirpath = pathlib.Path.cwd() / data_dirpath

    def setUp(self):
        # XXX: Work around TIME_WAIT state of connected sockets.
        socketserver.TCPServer.allow_reuse_address = True

    def tearDown(self):
        socketserver.TCPServer.allow_reuse_address = False

    def prepare(self, stack):
        stack.enter_context(suppress_stderr())
        stack.enter_context(change_dir(self.data_dirpath))
        stack.enter_context(start_server())
        self.executor = stack.enter_context(futures.ThreadPoolExecutor(1))
        self.root_dirpath = pathlib.Path(
            stack.enter_context(tempfile.TemporaryDirectory()))
        print('data_dirpath', self.data_dirpath, file=sys.stderr)
        print('root_dirpath', self.root_dirpath, file=sys.stderr)

    def test_download(self):
        relpath_to_requests = {
            'file1': [
                'http://localhost:8000/file1-not',
                'http://localhost:8000/file1-still-not',
                'http://localhost:8000/file1',
                'http://localhost:8000/file1-also-not',
            ],
            'path/to/file2-alias': [
                'http://localhost:8000/file2',
            ],
        }

        with contextlib.ExitStack() as stack:
            self.prepare(stack)

            utils.download(
                client=clients.Client(),
                executor=self.executor,
                output_dirpath=(self.root_dirpath / 'test'),
                relpath_to_requests=relpath_to_requests,
            )

            self.assertTrue(self.root_dirpath.is_dir())
            self.assertFileEqual(
                self.data_dirpath / 'file1',
                self.root_dirpath / 'test' / 'file1',
            )
            self.assertFileEqual(
                self.data_dirpath / 'file2',
                self.root_dirpath / 'test' / 'path/to/file2-alias',
            )
            paths = [
                str(path.relative_to(self.root_dirpath))
                for path in sorted(self.root_dirpath.glob('**/*'))
            ]
            self.assertListEqual(
                [
                    'test',
                    'test/file1',
                    'test/path',
                    'test/path/to',
                    'test/path/to/file2-alias',
                ],
                paths,
            )

    def test_downloader(self):
        """Test each step that download() takes."""
        relpath_to_requests = {
            'file1': ['http://localhost:8000/file1'],
            'file2': ['http://localhost:8000/file2'],
        }
        with contextlib.ExitStack() as stack:
            self.prepare(stack)
            client = clients.Client()

            output_dirpath = self.root_dirpath / 'test'

            dler = utils._Downloader(
                client=client,
                executor=self.executor,
                output_dirpath=output_dirpath,
                relpath_to_requests=relpath_to_requests,
                strict=True,
                chunk_size=10240)

            ### Test _Downloader.prepare()

            # prepare() skips existing dir.
            output_dirpath.mkdir(parents=True)
            self.assertFalse(dler.prepare())
            output_dirpath.rmdir()

            # prepare() errs on non-dir.
            output_dirpath.touch()
            with self.assertRaises(utils.DownloadError):
                dler.prepare()
            output_dirpath.unlink()

            # prepare() errs on non-dir.
            tmp_dirpath = output_dirpath.with_name(
                output_dirpath.name + '.part')
            tmp_dirpath.touch()
            with self.assertRaises(utils.DownloadError):
                dler.prepare()
            tmp_dirpath.unlink()

            self.assertTrue(dler.prepare())

            ### Test _Downloader.download()

            # download() skips existing file.
            file1_path = tmp_dirpath / 'file1'
            file1_path.touch()
            dler.download(tmp_dirpath)

            with file1_path.open() as file1:
                self.assertEqual('', file1.read())
            self.assertFileNotEqual(
                self.data_dirpath / 'file1',
                tmp_dirpath / 'file1',
            )
            self.assertFileEqual(
                self.data_dirpath / 'file2',
                tmp_dirpath / 'file2',
            )

            ### Test _Downloader.check()

            file3_path = tmp_dirpath / 'path/to/file3'
            file3_path.parent.mkdir(parents=True)
            file3_path.touch()

            dler.strict = False
            dler.check(tmp_dirpath)
            self.assertTrue(file3_path.exists())
            self.assertTrue(file3_path.parent.exists())
            self.assertTrue(file3_path.parent.parent.exists())

            # check() removes extra files when strict is True.
            dler.strict = True
            dler.check(tmp_dirpath)
            self.assertFalse(file3_path.exists())
            self.assertFalse(file3_path.parent.exists())
            self.assertFalse(file3_path.parent.parent.exists())

            paths = [
                str(path.relative_to(self.root_dirpath))
                for path in sorted(self.root_dirpath.glob('**/*'))
            ]
            self.assertListEqual(
                ['test.part', 'test.part/file1', 'test.part/file2'], paths
            )

            # check() errs on missing files.
            file1_path.unlink()
            with self.assertRaises(utils.DownloadError):
                dler.check(tmp_dirpath)

    def assertFileEqual(self, expect, actual):
        self.assertTrue(self.compare_file(expect, actual))

    def assertFileNotEqual(self, expect, actual):
        self.assertFalse(self.compare_file(expect, actual))

    def compare_file(self, expect, actual):
        expect = pathlib.Path(expect)
        actual = pathlib.Path(actual)
        self.assertTrue(expect.is_file())
        self.assertTrue(actual.is_file())
        return filecmp.cmp(str(expect), str(actual), shallow=False)


class FormTest(unittest.TestCase):

    @unittest.skipIf(skip_dom_parsing, 'lxml.etree is not installed')
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


if __name__ == '__main__':
    unittest.main()
