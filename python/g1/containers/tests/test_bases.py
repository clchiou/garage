import unittest

from g1.containers import bases

from tests import fixtures


class BasesTest(fixtures.TestCaseBase):

    def test_get_repo_path(self):
        self.assertEqual(
            bases.get_repo_path(),
            self.test_repo_path / bases.REPO_LAYOUT_VERSION,
        )

    def test_cmd_init(self):
        bases.cmd_init()
        self.assertTrue(self.test_repo_path.is_dir())
        path = self.test_repo_path / bases.REPO_LAYOUT_VERSION
        self.assertTrue(path.is_dir())
        self.assertEqual(path.stat().st_mode & 0o777, 0o750)
        self.assertEqual(
            sorted(p.name for p in self.test_repo_path.iterdir()),
            [bases.REPO_LAYOUT_VERSION],
        )


if __name__ == '__main__':
    unittest.main()
