import unittest

import tempfile
from pathlib import Path

from g1.containers import bases


class TestCaseBase(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.test_repo_tempdir = tempfile.TemporaryDirectory()
        self.test_repo_path = Path(self.test_repo_tempdir.name)
        bases.PARAMS.repository.unsafe_set(self.test_repo_tempdir.name)
        bases.PARAMS.use_root_privilege.unsafe_set(False)

    def tearDown(self):
        self.test_repo_tempdir.cleanup()
        super().tearDown()

    @staticmethod
    def list_dir(path):
        return sorted(p.name for p in path.iterdir())
