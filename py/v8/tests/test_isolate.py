import unittest

import threading

from . import v8


class IsolateTest(unittest.TestCase):

    def test_isolate(self):

        def run():
            with v8.isolate() as isolate, isolate.context() as context:
                barrier.wait()
                self.assertEqual(
                    'hello world', context.evaluate('"hello world"'))

        N = 3
        barrier = threading.Barrier(N)
        threads = [threading.Thread(target=run) for _ in range(N)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()


if __name__ == '__main__':
    unittest.main()
