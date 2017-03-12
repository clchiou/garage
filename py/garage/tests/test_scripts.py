import unittest

from pathlib import Path
import threading

from garage import scripts


class ScriptsTest(unittest.TestCase):

    def test_ensure_path(self):
        self.assertEqual(Path('/a/b/c'), scripts.ensure_path(Path('/a/b/c')))
        self.assertEqual(Path('/a/b/c'), scripts.ensure_path('/a/b/c'))
        self.assertIsNone(scripts.ensure_path(None))

    def test_ensure_str(self):
        self.assertEqual('', scripts.ensure_str(''))
        self.assertEqual('x', scripts.ensure_str('x'))
        self.assertEqual('x', scripts.ensure_str(Path('x')))
        self.assertIsNone(scripts.ensure_str(None))

    def test_make_command(self):
        self.assertEqual(['ls'], scripts.make_command(['ls']))
        with scripts.using_sudo():
            self.assertEqual(['sudo', 'ls'], scripts.make_command(['ls']))
            with scripts.using_sudo(False):
                self.assertEqual(['ls'], scripts.make_command(['ls']))

    def test_context(self):

        barrier = threading.Barrier(2)
        data = set()

        def f(path):
            with scripts.directory(path):
                data.add(scripts._get_context()[scripts.DIRECTORY])
                barrier.wait()

        with scripts.directory('p0'):
            t1 = threading.Thread(target=f, args=('p1',))
            t1.start()
            t2 = threading.Thread(target=f, args=('p2',))
            t2.start()
            t1.join()
            t2.join()

        self.assertEqual({Path('p1'), Path('p2')}, data)


if __name__ == '__main__':
    unittest.main()
