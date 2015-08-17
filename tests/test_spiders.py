import unittest

import contextlib
import pathlib
import socketserver

from garage import spiders

import tests.http.server


class TestParser(spiders.Parser):

    def __init__(self):
        self.logs = []

    def is_outside(self, uri, from_document=None):
        return not uri.startswith('http://localhost:8000')

    def parse(self, req, rep):
        self.logs.append(req)
        doc = spiders.Document()
        doc.identity = req.uri
        doc.links = [
            ('http://localhost:8000/%s' % link.get('href'), None)
            for link in rep.dom().xpath('//a')
        ]
        return doc


class SpidersTest(unittest.TestCase):

    data_dirpath = pathlib.Path(__file__).with_name('test_spiders_testdata')
    if not data_dirpath.is_absolute():
        data_dirpath = pathlib.Path.cwd() / data_dirpath

    def setUp(self):
        # XXX: Work around TIME_WAIT state of connected sockets.
        socketserver.TCPServer.allow_reuse_address = True

    def tearDown(self):
        socketserver.TCPServer.allow_reuse_address = False

    def test_spider(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(
                tests.http.server.suppress_stderr())
            stack.enter_context(
                tests.http.server.change_dir(self.data_dirpath))
            stack.enter_context(
                tests.http.server.start_server())

            parser = TestParser()
            spider = spiders.Spider(parser=parser)
            spider.crawl('http://localhost:8000/')
            spider.future.result()

            uris = set(req.uri for req in parser.logs)
            self.assertSetEqual(
                {
                    'http://localhost:8000/',
                    'http://localhost:8000/file1',
                    'http://localhost:8000/file2',
                    'http://localhost:8000/file3',
                },
                uris,
            )


if __name__ == '__main__':
    unittest.main()
