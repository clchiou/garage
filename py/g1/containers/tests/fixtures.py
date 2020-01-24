import unittest
import unittest.mock

import tempfile
from pathlib import Path

from g1.containers import bases


class TestCaseBase(unittest.TestCase):

    def setUp(self):
        super().setUp()
        unittest.mock.patch('g1.bases.oses.assert_group_exist').start()
        unittest.mock.patch('g1.bases.oses.assert_root_privilege').start()
        unittest.mock.patch('g1.containers.bases.chown_app').start()
        unittest.mock.patch('g1.containers.bases.chown_root').start()
        unittest.mock.patch('g1.scripts.assert_command_exist').start()
        self.test_repo_tempdir = tempfile.TemporaryDirectory()
        self.test_repo_path = Path(self.test_repo_tempdir.name)
        bases.PARAMS.repository.unsafe_set(self.test_repo_tempdir.name)

    def tearDown(self):
        self.test_repo_tempdir.cleanup()
        unittest.mock.patch.stopall()
        super().tearDown()

    @staticmethod
    def list_dir(path):
        return sorted(p.name for p in path.iterdir())
