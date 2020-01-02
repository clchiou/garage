import unittest

from pathlib import Path

from g1.scripts import utils


class UtilsTest(unittest.TestCase):

    def test_get_url_path(self):
        self.assertEqual(
            utils.get_url_path('http://x/y/z?a=1'),
            Path('/y/z'),
        )

    def test_guess(self):
        self.assertEqual(
            utils._guess('foo.tar.gz'),
            (utils.ArchiveTypes.TAR, utils.Compressors.GZIP),
        )
        self.assertEqual(
            utils._guess('foo.gz'),
            (utils.ArchiveTypes.UNKNOWN, utils.Compressors.GZIP),
        )
        self.assertEqual(
            utils._guess('foo.txt'),
            (utils.ArchiveTypes.UNKNOWN, utils.Compressors.UNKNOWN),
        )

    def test_remove_archive_suffix(self):
        self.assertEqual(
            utils.remove_archive_suffix('foo.tar.gz'),
            'foo',
        )
        self.assertEqual(
            utils.remove_archive_suffix('foo.txt'),
            'foo.txt',
        )
        self.assertEqual(
            utils.remove_archive_suffix('foo.txt.gz'),
            'foo.txt.gz',
        )


if __name__ == '__main__':
    unittest.main()
