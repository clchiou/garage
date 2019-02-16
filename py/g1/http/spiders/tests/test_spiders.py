import unittest
import unittest.mock

import heapq

from g1.asyncs import kernels
from g1.http import spiders


class SpiderTest(unittest.TestCase):

    MAX_NUM_TASKS = 4

    def setUp(self):

        async def mocked_send(request):
            self.requests.append(request)
            return self.response_mock

        self.requests = []
        self.response_mock = unittest.mock.Mock()

        # Use ``mocked_send`` because mocked methods cannot be awaited.
        self.session_mock = unittest.mock.Mock(spec_set=['send'])
        self.session_mock.send = mocked_send

    def make_spider(self, controller):
        return spiders.Spider(
            controller,
            session=self.session_mock,
            max_num_tasks=self.MAX_NUM_TASKS,
        )

    @kernels.with_kernel
    def test_crawl_nothing(self):

        # Use ``wraps`` because mocked methods cannot be awaited.
        controller_mock = unittest.mock.Mock(wraps=spiders.Controller())
        spider = self.make_spider(controller_mock)

        self.assertIsNone(kernels.run(spider.crawl, timeout=1))

        controller_mock.on_crawl_start.assert_called_once_with(spider)
        controller_mock.on_request_not_sent.assert_not_called()
        controller_mock.on_request_error.assert_not_called()
        controller_mock.on_response.assert_not_called()
        controller_mock.on_crawl_stop.assert_called_once_with(
            spider, None, None, None
        )

        self.assertEqual(self.requests, [])

    @kernels.with_kernel
    def test_crawl(self):

        links = {
            'foo.html': ['bar.html', '0.html'],
            'bar.html': ['spam.html', 'egg.html'],
            'spam.html': ['foo.html'],
            'egg.html': ['foo.html', 'bar.html'],
        }
        for i in range(100):
            links['%d.html' % i] = ['%d.html' % (i + 1), 'bar.html']
        links['100.html'] = ['bar.html']

        class TestController(spiders.Controller):

            async def on_crawl_start(self, spider):
                spider.enqueue(priority=0, request='foo.html')

            async def on_response(self, spider, job_id, request, response):
                for url in links[request.url]:
                    spider.enqueue(priority=0, request=url)

        # Use ``wraps`` because mocked methods cannot be awaited.
        controller_mock = unittest.mock.Mock(wraps=TestController())
        spider = self.make_spider(controller_mock)

        self.assertIsNone(kernels.run(spider.crawl, timeout=1))

        controller_mock.on_crawl_start.assert_called_once_with(spider)
        controller_mock.on_request_not_sent.assert_called_with(
            spider,
            unittest.mock.ANY,
            unittest.mock.ANY,
        )
        controller_mock.on_request_error.assert_not_called()
        controller_mock.on_response.assert_called_with(
            spider,
            unittest.mock.ANY,
            unittest.mock.ANY,
            self.response_mock,
        )
        controller_mock.on_crawl_stop.assert_called_once_with(
            spider, None, None, None
        )

        # Every URL is requested exactly once.
        expect_urls = ['foo.html', 'bar.html', 'spam.html', 'egg.html']
        expect_urls.extend('%d.html' % i for i in range(101))
        expect_urls.sort()
        self.assertEqual(
            sorted(request.url for request in self.requests),
            expect_urls,
        )

    @kernels.with_kernel
    def test_dependencies(self):

        actual_job_ids = []
        expect_job_ids = []

        class TestController(spiders.Controller):

            async def on_crawl_start(self, spider):
                job_ids = [spider.enqueue(priority=i) for i in range(100)]
                expect_job_ids.extend(job_ids)
                expect_job_ids.append(
                    spider.enqueue(priority=-1, dependencies=job_ids)
                )

            async def on_response(self, spider, job_id, request, response):
                actual_job_ids.append(job_id)

        # Use ``wraps`` because mocked methods cannot be awaited.
        controller_mock = unittest.mock.Mock(wraps=TestController())
        spider = self.make_spider(controller_mock)

        self.assertIsNone(kernels.run(spider.crawl, timeout=1))

        controller_mock.on_response.assert_called_with(
            spider,
            unittest.mock.ANY,
            None,
            None,
        )

        self.assertEqual(self.requests, [])

        self.assertEqual(actual_job_ids, expect_job_ids)

    @kernels.with_kernel
    def test_request_shutdown(self):

        class TestController(spiders.Controller):

            def __init__(self, graceful):
                self.graceful = graceful

            async def on_crawl_start(self, spider):
                for i in range(100):
                    spider.enqueue(priority=i, request='%d.html' % i)

            async def on_response(self, spider, job_id, request, response):
                spider.request_shutdown(graceful=self.graceful)

        for graceful in (True, False):
            with self.subTest(graceful=graceful):

                self.requests.clear()

                # Use ``wraps`` because mocked methods cannot be awaited.
                controller_mock = unittest.mock.Mock(
                    wraps=TestController(graceful)
                )
                spider = self.make_spider(controller_mock)

                self.assertIsNone(kernels.run(spider.crawl, timeout=1))

                if graceful:
                    self.assertEqual(
                        [request.url for request in self.requests],
                        ['%d.html' % i for i in range(self.MAX_NUM_TASKS)],
                    )
                else:
                    self.assertEqual(
                        [request.url for request in self.requests],
                        ['0.html'],
                    )


class RequestIdCheckerTest(unittest.TestCase):

    def test_dont_check_request_id(self):
        for rid in (1, 2, 3):
            self.assertFalse(spiders.dont_check_request_id(rid))
            self.assertFalse(spiders.dont_check_request_id(rid))

    def test_request_id_checker(self):
        checker = spiders.RequestIdChecker()
        for rid in (1, 2, 3):
            self.assertFalse(checker(rid))
            self.assertTrue(checker(rid))


class JobTest(unittest.TestCase):

    @staticmethod
    def make_job(priority):
        return spiders.Job(
            id=None,
            priority=priority,
            request_id=None,
            request=None,
            dependencies=None,
        )

    def test_job(self):
        j1 = self.make_job(1)
        self.assertNotEqual(j1, self.make_job(1))
        self.assertLess(j1, self.make_job(2))

    def test_heap(self):
        js = []
        for i in (6, 1, 4, 3, 2, 5):
            heapq.heappush(js, self.make_job(i))
        ps = []
        while js:
            ps.append(heapq.heappop(js).priority)
        self.assertEqual(ps, [1, 2, 3, 4, 5, 6])


if __name__ == '__main__':
    unittest.main()
