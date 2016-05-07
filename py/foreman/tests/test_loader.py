import unittest

from pathlib import Path

from foreman import Searcher


class SearcherTest(unittest.TestCase):

    def test_searcher(self):
        testdata = Path(__file__).parent / 'testdata'
        self.assertTrue(testdata.is_dir())

        search = Searcher([testdata / 'path2', testdata / 'path1'])

        self.assertTrue(search('pkg1').is_file())
        self.assertTrue(search('pkg1/pkg2').is_file())
        self.assertTrue(search('pkg3').is_file())
        with self.assertRaises(FileNotFoundError):
            search('pkg-no-build-file')

        # Test search path order.
        self.assertTrue(str(search('pkg1')).endswith('path1/pkg1/build.py'))
        self.assertTrue(str(search('pkg3')).endswith('path2/pkg3/build.py'))


if __name__ == '__main__':
    unittest.main()
