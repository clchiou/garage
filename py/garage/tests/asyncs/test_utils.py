import unittest

from garage.threads.executors import WorkerPool
from garage.asyncs.executors import WorkerPoolAdapter
from garage.asyncs.utils import (
    IteratorAdapter,
    synchronous,
)


class UtilsTest(unittest.TestCase):

    def setUp(self):
        self.worker_pool = WorkerPoolAdapter(WorkerPool())

    def tearDown(self):
        self.worker_pool.shutdown(self)

    @synchronous
    async def test_iterator_adapter(self):
        async with self.worker_pool.make_executor(1) as executor:
            expect = 1
            async for actual in IteratorAdapter(executor, iter([1, 2, 3])):
                self.assertEqual(expect, actual)
                expect += 1


if __name__ == '__main__':
    unittest.main()
