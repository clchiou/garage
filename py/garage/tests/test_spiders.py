import unittest

from tests.availability import lxml_available, requests_available

import contextlib
import pathlib
import socketserver

if requests_available:

    from garage import spiders
    from garage.threads import queues
    import tests.http.server

    class TestParser(spiders.Parser):

        def __init__(self):
            self.logs = []

        def is_outside(self, uri, from_document=None):
            return not uri.startswith('http://localhost:8000')

        def parse(self, req, rep):
            self.logs.append(req)
            return spiders.Document(identity=req.uri, links=[
                ('http://localhost:8000/%s' % link.get('href'), None)
                for link in rep.dom().xpath('//a')
            ])


@unittest.skipUnless(requests_available, 'requests unavailable')
class SpidersTest(unittest.TestCase):

    data_dirpath = pathlib.Path(__file__).with_name('test_spiders_testdata')
    if not data_dirpath.is_absolute():
        data_dirpath = pathlib.Path.cwd() / data_dirpath

    def setUp(self):
        # XXX: Work around TIME_WAIT state of connected sockets.
        socketserver.TCPServer.allow_reuse_address = True

    def tearDown(self):
        socketserver.TCPServer.allow_reuse_address = False

    @unittest.skipUnless(lxml_available, 'lxml unavailable')
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
            spider.start()
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


@unittest.skipUnless(requests_available, 'requests unavailable')
class TaskTest(unittest.TestCase):

    def test_task(self):
        t_lp = spiders.Task(None, None, None)
        t_0 = spiders.Task(None, None, 0)
        t_1 = spiders.Task(None, None, 1)

        self.assertLess(t_0, t_lp)
        self.assertLess(t_1, t_lp)
        self.assertLess(t_0, t_1)
        self.assertGreater(t_lp, t_0)
        self.assertGreater(t_lp, t_1)
        self.assertGreater(t_1, t_0)

        pqueue = queues.PriorityQueue()
        pqueue.put(t_lp)
        pqueue.put(t_1)
        pqueue.put(t_0)
        self.assertEqual(t_0, pqueue.get())
        self.assertEqual(t_1, pqueue.get())
        self.assertEqual(t_lp, pqueue.get())

        self.assertNotEqual(
            spiders.Task(None, None, None),
            spiders.Task(None, None, None),
        )

        self.assertNotEqual(
            spiders.Task(None, None, 0),
            spiders.Task(None, None, 0),
        )


if __name__ == '__main__':
    unittest.main()
