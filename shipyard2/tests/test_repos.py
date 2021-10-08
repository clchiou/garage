import unittest

import shutil
import tempfile
from pathlib import Path

import foreman

import shipyard2
from shipyard2.releases import repos


class ReposTest(unittest.TestCase):

    FOO_BAR = foreman.Label.parse('//foo:bar')
    SOME_DATA = foreman.Label.parse('//some:data')
    SPAM_EGG = foreman.Label.parse('//spam:egg')

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.repo_path = Path(self._tempdir.__enter__()) / 'releases'
        shutil.copytree(
            Path(__file__).parent / 'testdata',
            self.repo_path,
            symlinks=True,
        )

    def tearDown(self):
        self._tempdir.__exit__(None, None, None)

    def get_pod_dir(self, relpath):
        top_path = self.repo_path / shipyard2.RELEASE_PODS_DIR_NAME
        return repos.PodDir(top_path, top_path / relpath)

    def get_xar_dir(self, relpath):
        top_path = self.repo_path / shipyard2.RELEASE_XARS_DIR_NAME
        return repos.XarDir(top_path, top_path / relpath)

    def get_builder_image_dir(self, relpath):
        top_path = self.repo_path / shipyard2.RELEASE_IMAGES_DIR_NAME
        return repos.BuilderImageDir(top_path, top_path / relpath)

    def get_image_dir(self, relpath):
        top_path = self.repo_path / shipyard2.RELEASE_IMAGES_DIR_NAME
        return repos.ImageDir(top_path, top_path / relpath)

    def get_volume_dir(self, relpath):
        top_path = self.repo_path / shipyard2.RELEASE_VOLUMES_DIR_NAME
        return repos.VolumeDir(top_path, top_path / relpath)

    def test_envs_dir(self):
        envs_dir = repos.EnvsDir(self.repo_path)
        self.assertEqual(envs_dir.envs, ['production'])
        self.assertEqual(
            envs_dir.sort_pod_dirs('production'),
            [self.get_pod_dir('foo/bar/0.0.1')],
        )
        self.assertEqual(envs_dir.sort_xar_dirs('production'), [])
        self.assertTrue(envs_dir.has_release('production', self.FOO_BAR))
        self.assertEqual(
            envs_dir.get_current_pod_versions(),
            {self.FOO_BAR: {'0.0.1'}},
        )
        self.assertEqual(
            envs_dir.get_current_xar_versions(),
            {},
        )

        envs_dir.release_pod('production', self.FOO_BAR, '0.0.2')
        self.assertEqual(
            envs_dir.sort_pod_dirs('production'),
            [self.get_pod_dir('foo/bar/0.0.2')],
        )
        self.assertEqual(envs_dir.sort_xar_dirs('production'), [])
        self.assertTrue(envs_dir.has_release('production', self.FOO_BAR))
        self.assertEqual(
            envs_dir.get_current_pod_versions(),
            {self.FOO_BAR: {'0.0.2'}},
        )
        self.assertEqual(
            envs_dir.get_current_xar_versions(),
            {},
        )

        envs_dir.release_xar('production', self.FOO_BAR, '0.0.3')
        self.assertEqual(envs_dir.sort_pod_dirs('production'), [])
        self.assertEqual(
            envs_dir.sort_xar_dirs('production'),
            [self.get_xar_dir('foo/bar/0.0.3')],
        )
        self.assertTrue(envs_dir.has_release('production', self.FOO_BAR))
        self.assertEqual(
            envs_dir.get_current_pod_versions(),
            {},
        )
        self.assertEqual(
            envs_dir.get_current_xar_versions(),
            {self.FOO_BAR: {'0.0.3'}},
        )

        envs_dir.unrelease('production', self.FOO_BAR)
        self.assertEqual(envs_dir.sort_pod_dirs('production'), [])
        self.assertEqual(envs_dir.sort_xar_dirs('production'), [])
        self.assertFalse(envs_dir.has_release('production', self.FOO_BAR))
        self.assertEqual(
            envs_dir.get_current_pod_versions(),
            {},
        )
        self.assertEqual(
            envs_dir.get_current_xar_versions(),
            {},
        )

    def test_pod_dir(self):
        d1 = self.get_pod_dir('foo/bar/0.0.1')
        d2 = self.get_pod_dir('foo/bar/0.0.2')
        self.assertEqual(repos.PodDir.sort_dirs(self.repo_path), [d1, d2])
        self.assertEqual(
            repos.PodDir.group_dirs(self.repo_path),
            {self.FOO_BAR: [d1, d2]},
        )
        self.assertEqual(d1.label, self.FOO_BAR)
        self.assertEqual(d1.version, '0.0.1')
        self.assertEqual(
            list(d1.iter_image_dirs()),
            [self.get_image_dir('spam/egg/0.0.1')],
        )
        self.assertEqual(
            list(d1.iter_volume_dirs()),
            [self.get_volume_dir('some/data/0.0.1')],
        )
        d1.remove()
        self.assertEqual(repos.PodDir.sort_dirs(self.repo_path), [d2])

    def test_xar_dir(self):
        d = self.get_xar_dir('foo/bar/0.0.3')
        self.assertEqual(repos.XarDir.sort_dirs(self.repo_path), [d])
        self.assertEqual(
            repos.XarDir.group_dirs(self.repo_path),
            {self.FOO_BAR: [d]},
        )
        self.assertEqual(d.label, self.FOO_BAR)
        self.assertEqual(d.version, '0.0.3')
        self.assertEqual(
            d.get_image_dir(),
            self.get_image_dir('spam/egg/0.0.1'),
        )
        d.remove()
        self.assertEqual(repos.XarDir.sort_dirs(self.repo_path), [])

    def test_builder_image_dir(self):
        d = self.get_builder_image_dir('spam/egg/0.0.2')
        self.assertEqual(repos.BuilderImageDir.sort_dirs(self.repo_path), [d])
        self.assertEqual(
            repos.BuilderImageDir.group_dirs(self.repo_path),
            {self.SPAM_EGG: [d]},
        )
        self.assertEqual(d.label, self.SPAM_EGG)
        self.assertEqual(d.version, '0.0.2')
        d.remove()
        self.assertEqual(repos.BuilderImageDir.sort_dirs(self.repo_path), [])

    def test_image_dir(self):
        d = self.get_image_dir('spam/egg/0.0.1')
        self.assertEqual(repos.ImageDir.sort_dirs(self.repo_path), [d])
        self.assertEqual(
            repos.ImageDir.group_dirs(self.repo_path),
            {self.SPAM_EGG: [d]},
        )
        self.assertEqual(d.label, self.SPAM_EGG)
        self.assertEqual(d.version, '0.0.1')
        d.remove()
        self.assertEqual(repos.ImageDir.sort_dirs(self.repo_path), [])

    def test_volume_dir(self):
        d = self.get_volume_dir('some/data/0.0.1')
        self.assertEqual(repos.VolumeDir.sort_dirs(self.repo_path), [d])
        self.assertEqual(
            repos.VolumeDir.group_dirs(self.repo_path),
            {self.SOME_DATA: [d]},
        )
        self.assertEqual(d.label, self.SOME_DATA)
        self.assertEqual(d.version, '0.0.1')
        d.remove()
        self.assertEqual(repos.VolumeDir.sort_dirs(self.repo_path), [])


if __name__ == '__main__':
    unittest.main()
