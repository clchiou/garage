import unittest
import unittest.mock

import tempfile
from pathlib import Path

from g1.operations import bases


class TestCaseBase(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self._test_dir_tempdir = tempfile.TemporaryDirectory()
        test_dir_path = Path(self._test_dir_tempdir.name)
        self.test_repo_path = test_dir_path / 'repo'
        self.test_repo_path.mkdir()
        bases.PARAMS.repository.unsafe_set(self.test_repo_path)
        self.test_zipapp_dir_path = test_dir_path / 'bin'
        self.test_zipapp_dir_path.mkdir()
        bases.PARAMS.zipapp_directory.unsafe_set(self.test_zipapp_dir_path)
        self.test_bundle_dir_path = test_dir_path / 'bundle'
        self.test_bundle_dir_path.mkdir()
        self.test_ops_dir_path = test_dir_path / 'ops-dir'
        self.test_ops_dir_path.mkdir()
        unittest.mock.patch('g1.operations.bases._chown').start()

    def tearDown(self):
        self._test_dir_tempdir.cleanup()
        unittest.mock.patch.stopall()
        super().tearDown()

    @staticmethod
    def list_dir(path):
        return sorted(p.name for p in path.iterdir())
