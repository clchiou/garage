import unittest

import datetime
import shutil
import time
from pathlib import Path

from g1.bases import datetimes
from g1.containers import bases
from g1.containers import images

from tests import fixtures


class ImagesTest(fixtures.TestCaseBase):

    sample_image_id = '0123456789abcdef' * 4

    sample_metadata = images.ImageMetadata(
        name='sample-app',
        version='1.0',
    )

    def setUp(self):
        super().setUp()
        bases.cmd_init()
        images.cmd_init()
        self.sample_image_dir_path = images.get_image_dir_path(
            self.sample_image_id
        )

    def create_image_dir(self, image_id, metadata=None):
        image_dir_path = images.get_image_dir_path(image_id)
        image_dir_path.mkdir()
        bases.write_jsonobject(
            metadata or self.sample_metadata,
            images.get_metadata_path(image_dir_path),
        )
        images.get_rootfs_path(image_dir_path).mkdir()

    @staticmethod
    def list_image_dir_paths():
        return sorted(p.name for p in images.iter_image_dir_paths())

    @staticmethod
    def list_tag_paths():
        return sorted(p.name for p in images.get_tags_path().iterdir())

    #
    # Top-level commands.
    #

    def test_cmd_init(self):
        self.assertTrue(images.get_image_repo_path().is_dir())
        self.assertEqual(
            images.get_image_repo_path().stat().st_mode & 0o777,
            0o750,
        )
        self.assertEqual(
            self.list_dir(images.get_image_repo_path()),
            ['tags', 'tmp', 'trees'],
        )

    def test_cmd_import(self):
        path = images.get_image_repo_path() / 'archive'
        path.mkdir()
        bases.write_jsonobject(
            self.sample_metadata, images.get_metadata_path(path)
        )
        images.get_rootfs_path(path).mkdir()
        shutil.make_archive(path, 'gztar', path)

        self.assertEqual(self.list_image_dir_paths(), [])
        self.assertEqual(self.list_tag_paths(), [])

        images.cmd_import(path.with_suffix('.tar.gz'))
        image_ids_1 = self.list_image_dir_paths()
        self.assertEqual(len(image_ids_1), 1)
        self.assertEqual(self.list_tag_paths(), [])

        images.cmd_import(path.with_suffix('.tar.gz'))
        image_ids_2 = self.list_image_dir_paths()
        self.assertEqual(image_ids_1, image_ids_2)
        self.assertEqual(self.list_tag_paths(), [])

        self.assertEqual(
            images.read_metadata(images.get_image_dir_path(image_ids_1[0])),
            self.sample_metadata,
        )

    def test_cmd_list(self):

        def cmd_list():
            return sorted((result['id'], result['tags'])
                          for result in images.cmd_list())

        image_id_1 = '%064d' % 1
        image_id_2 = '%064d' % 2

        self.assertEqual(cmd_list(), [])

        self.create_image_dir(image_id_1)
        self.assertEqual(cmd_list(), [(image_id_1, [])])

        self.create_image_dir(image_id_2)
        self.assertEqual(cmd_list(), [(image_id_1, []), (image_id_2, [])])

        images.cmd_tag(image_id=image_id_1, new_tag='hello-world')
        self.assertEqual(
            cmd_list(),
            [(image_id_1, ['hello-world']), (image_id_2, [])],
        )

        images.cmd_tag(image_id=image_id_2, new_tag='hello-world')
        self.assertEqual(
            cmd_list(),
            [(image_id_1, []), (image_id_2, ['hello-world'])],
        )

    def test_cmd_tag(self):
        self.create_image_dir(self.sample_image_id)
        self.assertEqual(self.list_image_dir_paths(), [self.sample_image_id])
        self.assertEqual(self.list_tag_paths(), [])

        images.cmd_tag(image_id=self.sample_image_id, new_tag='tag-2')
        self.assertEqual(self.list_image_dir_paths(), [self.sample_image_id])
        self.assertEqual(self.list_tag_paths(), ['tag-2'])

        images.cmd_tag(image_id=self.sample_image_id, new_tag='tag-1')
        self.assertEqual(self.list_image_dir_paths(), [self.sample_image_id])
        self.assertEqual(self.list_tag_paths(), ['tag-1', 'tag-2'])

    def test_cmd_remove_tag(self):
        self.create_image_dir(self.sample_image_id)
        self.assertEqual(self.list_image_dir_paths(), [self.sample_image_id])
        self.assertEqual(self.list_tag_paths(), [])

        images.cmd_tag(image_id=self.sample_image_id, new_tag='some-tag')
        self.assertEqual(self.list_image_dir_paths(), [self.sample_image_id])
        self.assertEqual(self.list_tag_paths(), ['some-tag'])

        images.cmd_remove_tag('some-tag')
        self.assertEqual(self.list_image_dir_paths(), [self.sample_image_id])
        self.assertEqual(self.list_tag_paths(), [])

        images.cmd_remove_tag('some-tag')
        self.assertEqual(self.list_image_dir_paths(), [self.sample_image_id])
        self.assertEqual(self.list_tag_paths(), [])

    def test_cmd_remove(self):
        self.create_image_dir(self.sample_image_id)
        images.cmd_tag(image_id=self.sample_image_id, new_tag='some-tag')
        self.assertEqual(self.list_image_dir_paths(), [self.sample_image_id])
        self.assertEqual(self.list_tag_paths(), ['some-tag'])

        images.cmd_remove(image_id=self.sample_image_id)
        self.assertEqual(self.list_image_dir_paths(), [])
        self.assertEqual(self.list_tag_paths(), [])

    def test_cmd_cleanup(self):
        self.create_image_dir(self.sample_image_id)
        images.cmd_tag(image_id=self.sample_image_id, new_tag='some-tag')
        self.assertEqual(self.list_image_dir_paths(), [self.sample_image_id])
        self.assertEqual(self.list_tag_paths(), ['some-tag'])

        images.cmd_cleanup(datetimes.utcnow() + datetime.timedelta(days=1))
        self.assertEqual(self.list_image_dir_paths(), [])
        self.assertEqual(self.list_tag_paths(), [])

    #
    # Locking strategy.
    #

    def test_using_tmp(self):
        tmp_dir_path = images.get_tmp_path()
        self.assertTrue(self.check_shared(tmp_dir_path))
        self.assertTrue(self.check_exclusive(tmp_dir_path))
        with images.using_tmp() as tmp_path:
            self.assertTrue(self.check_shared(tmp_dir_path))
            self.assertTrue(self.check_exclusive(tmp_dir_path))
            self.assertFalse(self.check_shared(tmp_path))
            self.assertFalse(self.check_exclusive(tmp_path))
            self.assertTrue(tmp_path.is_dir())
            self.assertEqual(tmp_path.parent, tmp_dir_path)
        self.assertTrue(self.check_shared(tmp_dir_path))
        self.assertTrue(self.check_exclusive(tmp_dir_path))
        self.assertFalse(tmp_path.exists())

    #
    # Data type.
    #

    def test_validate(self):

        for test_data in (
            '0' * 64,
            '0123456789abcdef' * 4,
        ):
            with self.subTest(test_data):
                self.assertEqual(images.validate_id(test_data), test_data)

        for test_data in (
            '',
            '0' * 63,
            '0' * 63 + 'x',
            'A' * 64,
            '0123456789ABCDEF' * 4,
        ):
            with self.subTest(test_data):
                with self.assertRaisesRegex(
                    AssertionError, r'expect .*fullmatch*.'
                ):
                    images.validate_id(test_data)

        self.do_test_validate(images.validate_name)

        self.do_test_validate(images.validate_version)
        self.assertEqual(images.validate_version('0.0.1'), '0.0.1')

        self.do_test_validate(images.validate_tag)

        for test_data in (
            {
                'name': '',
                'version': '',
            },
            {
                'name': 'A',
                'version': '',
            },
        ):
            with self.subTest(test_data):
                with self.assertRaisesRegex(
                    AssertionError, r'expect .*fullmatch*.'
                ):
                    images.ImageMetadata(**test_data)

    def do_test_validate(self, validate):

        for test_data in (
            '0',
            'x',
            'hello',
            'h-e-l-l-o-0-1-2-3-4',
        ):
            with self.subTest(test_data):
                self.assertEqual(validate(test_data), test_data)

        for test_data in (
            '',
            ':',
            'A',
            'a--b',
        ):
            with self.subTest(test_data):
                with self.assertRaisesRegex(
                    AssertionError, r'expect .*fullmatch*.'
                ):
                    validate(test_data)

    #
    # Repo layout.
    #

    def test_repo_layout(self):
        for path1, path2 in (
            (
                images.get_image_repo_path(),
                bases.get_repo_path() / 'images',
            ),
            (
                images.get_tags_path(),
                images.get_image_repo_path() / 'tags',
            ),
            (
                images.get_trees_path(),
                images.get_image_repo_path() / 'trees',
            ),
            (
                images.get_tmp_path(),
                images.get_image_repo_path() / 'tmp',
            ),
            (
                images.get_image_dir_path(self.sample_image_id),
                images.get_trees_path() / self.sample_image_id,
            ),
            (
                images.get_id(self.sample_image_dir_path),
                self.sample_image_id,
            ),
            (
                images.get_metadata_path(self.sample_image_dir_path),
                images.get_trees_path() / self.sample_image_id / 'metadata',
            ),
            (
                images.get_rootfs_path(self.sample_image_dir_path),
                images.get_trees_path() / self.sample_image_id / 'rootfs',
            ),
            (
                images.get_tag_path('some-tag'),
                images.get_tags_path() / 'some-tag',
            ),
            (
                images.get_tag(images.get_tag_path('some-tag')),
                'some-tag',
            ),
            (
                images.get_tag_target(self.sample_image_dir_path),
                Path('..') / 'trees' / self.sample_image_id,
            ),
        ):
            with self.subTest((path1, path2)):
                self.assertEqual(path1, path2)

    #
    # Top-level directories.
    #

    def test_cleanup_tags(self):
        tags_path = images.get_tags_path()
        self.assertEqual(self.list_dir(tags_path), [])

        images.cleanup_tags()
        self.assertEqual(self.list_dir(tags_path), [])

        (tags_path / 'some-dir').mkdir()
        (tags_path / 'some-file').touch()
        (tags_path / 'some-link').symlink_to('no-such-file')
        (tags_path / 'some-tag').symlink_to('../trees')
        self.assertEqual(
            self.list_dir(tags_path),
            ['some-dir', 'some-file', 'some-link', 'some-tag'],
        )

        images.cleanup_tags()
        self.assertEqual(self.list_dir(tags_path), ['some-tag'])

    def test_cleanup_tmp(self):
        tmp_path = images.get_tmp_path()
        self.assertEqual(self.list_dir(tmp_path), [])

        (tmp_path / 'some-dir').mkdir()
        (tmp_path / 'some-file').touch()
        self.assertEqual(self.list_dir(tmp_path), ['some-dir', 'some-file'])

        lock = bases.FileLock(tmp_path / 'some-dir')
        try:
            lock.acquire_shared()
            images.cleanup_tmp()
            self.assertEqual(self.list_dir(tmp_path), ['some-dir'])
        finally:
            lock.release()
            lock.close()

        images.cleanup_tmp()
        self.assertEqual(self.list_dir(tmp_path), [])

    def test_cleanup_trees(self):
        now = datetimes.utcnow()
        past = now - datetime.timedelta(days=1)
        future = now + datetime.timedelta(days=1)

        trees_path = images.get_trees_path()
        self.assertEqual(self.list_dir(trees_path), [])

        images.cleanup_trees(future)
        self.assertEqual(self.list_dir(trees_path), [])

        self.create_image_dir(self.sample_image_id)
        (trees_path / 'some-file').touch()
        self.assertEqual(
            self.list_dir(trees_path),
            [self.sample_image_id, 'some-file'],
        )

        images.cleanup_trees(past)
        self.assertEqual(self.list_dir(trees_path), [self.sample_image_id])

        images.cleanup_trees(future)
        self.assertEqual(self.list_dir(trees_path), [])

    #
    # Image directories.
    #

    def test_maybe_import_image_dir(self):

        def create_src_dir(src_path):
            src_path.mkdir()
            bases.write_jsonobject(
                self.sample_metadata, images.get_metadata_path(src_path)
            )

        trees_path = images.get_trees_path()
        self.assertEqual(self.list_dir(trees_path), [])

        src_path = images.get_image_repo_path() / 'some-path'
        create_src_dir(src_path)
        self.assertTrue(
            images.maybe_import_image_dir(src_path, self.sample_image_id)
        )
        self.assertFalse(src_path.exists())
        self.assertEqual(self.list_dir(trees_path), [self.sample_image_id])

        src_path = images.get_image_repo_path() / 'some-other-path'
        create_src_dir(src_path)
        self.assertFalse(
            images.maybe_import_image_dir(src_path, self.sample_image_id)
        )
        self.assertTrue(src_path.is_dir())
        self.assertEqual(self.list_dir(trees_path), [self.sample_image_id])

    def test_assert_unique_name_and_version(self):
        self.create_image_dir(self.sample_image_id)
        with self.assertRaisesRegex(
            AssertionError, r'expect unique image name and version'
        ):
            images.assert_unique_name_and_version(self.sample_metadata)

    def test_iter_image_dir_paths(self):

        image_id_1 = '%064d' % 1
        image_id_2 = '%064d' % 2
        image_id_3 = '%064d' % 3
        image_id_4 = '%064d' % 4
        image_id_5 = '%064d' % 5

        images.get_image_dir_path(image_id_4).touch()
        images.get_image_dir_path(image_id_5).touch()

        self.assertEqual(self.list_image_dir_paths(), [])

        self.create_image_dir(image_id_2)
        self.assertEqual(self.list_image_dir_paths(), [image_id_2])

        self.create_image_dir(image_id_1)
        self.assertEqual(self.list_image_dir_paths(), [image_id_1, image_id_2])

        self.create_image_dir(image_id_3)
        self.assertEqual(
            self.list_image_dir_paths(), [image_id_1, image_id_2, image_id_3]
        )

    def test_find_image_dir_path(self):

        def check_find_image_dir_path(image_id, name, version, tag, expect):
            self.assertEqual(
                images.find_image_dir_path(image_id, None, None, None),
                expect,
            )
            self.assertEqual(
                images.find_image_dir_path(None, name, version, None),
                expect,
            )
            self.assertEqual(
                images.find_image_dir_path(None, None, None, tag),
                expect,
            )
            self.assertEqual(
                images.find_id(name=name, version=version),
                image_id if expect else None,
            )
            self.assertEqual(
                images.find_id(tag=tag),
                image_id if expect else None,
            )
            self.assertEqual(
                images.find_name_and_version(image_id=image_id),
                (name, version) if expect else (None, None),
            )
            self.assertEqual(
                images.find_name_and_version(tag=tag),
                (name, version) if expect else (None, None),
            )

        with self.assertRaisesRegex(AssertionError, r'expect only one true'):
            images.find_image_dir_path(None, None, None, None)
        with self.assertRaisesRegex(AssertionError, r'expect only one true'):
            images.find_image_dir_path('', '', '', '')
        with self.assertRaisesRegex(AssertionError, r'expect only one true'):
            images.find_image_dir_path('x', 'y', '', '')
        with self.assertRaisesRegex(AssertionError, r'expect only one true'):
            images.find_image_dir_path('', '', 'y', 'z')
        with self.assertRaisesRegex(AssertionError, r'expect.*xor.*false'):
            images.find_image_dir_path('', 'x', '', '')

        check_find_image_dir_path(
            self.sample_image_id,
            'sample-app',
            '1.0',
            'some-tag',
            None,
        )

        self.create_image_dir(self.sample_image_id)
        tag_path = images.get_tag_path('some-tag')
        tag_path.symlink_to(images.get_tag_target(self.sample_image_dir_path))

        check_find_image_dir_path(
            self.sample_image_id,
            'sample-app',
            '1.0',
            'some-tag',
            self.sample_image_dir_path,
        )

    def test_maybe_remove_image_dir(self):
        some_path = images.get_image_repo_path() / 'some-path'

        tag_path_1 = images.get_tag_path('some-tag-1')
        tag_path_2 = images.get_tag_path('some-tag-2')

        tag_path_1.symlink_to(
            images.get_tag_target(self.sample_image_dir_path)
        )
        tag_path_2.symlink_to(
            images.get_tag_target(self.sample_image_dir_path)
        )
        self.assertTrue(bases.lexists(tag_path_1))
        self.assertTrue(bases.lexists(tag_path_2))

        self.assertTrue(
            images.maybe_remove_image_dir(self.sample_image_dir_path)
        )
        self.assertFalse(bases.lexists(tag_path_1))
        self.assertFalse(bases.lexists(tag_path_2))

        self.create_image_dir(self.sample_image_id)
        tag_path_1.symlink_to(
            images.get_tag_target(self.sample_image_dir_path)
        )
        tag_path_2.symlink_to(
            images.get_tag_target(self.sample_image_dir_path)
        )
        self.assertTrue(bases.lexists(tag_path_1))
        self.assertTrue(bases.lexists(tag_path_2))

        images.add_ref(self.sample_image_id, some_path)

        self.assertFalse(
            images.maybe_remove_image_dir(self.sample_image_dir_path)
        )
        self.assertTrue(self.sample_image_dir_path.is_dir())
        self.assertTrue(bases.lexists(tag_path_1))
        self.assertTrue(bases.lexists(tag_path_2))

        some_path.unlink()

        self.assertTrue(
            images.maybe_remove_image_dir(self.sample_image_dir_path)
        )
        self.assertFalse(self.sample_image_dir_path.is_dir())
        self.assertFalse(bases.lexists(tag_path_1))
        self.assertFalse(bases.lexists(tag_path_2))

    #
    # Metadata.
    #

    def test_iter_metadatas(self):

        def list_metadatas():
            return sorted(
                ((images.get_id(p), m) for p, m in images.iter_metadatas()),
                key=lambda args: args[0],
            )

        image_id_1 = '%064d' % 1
        image_id_2 = '%064d' % 2
        image_id_3 = '%064d' % 3

        self.assertEqual(list_metadatas(), [])

        self.create_image_dir(image_id_2)
        self.assertEqual(
            list_metadatas(),
            [
                (image_id_2, self.sample_metadata),
            ],
        )

        self.create_image_dir(image_id_1)
        self.assertEqual(
            list_metadatas(),
            [
                (image_id_1, self.sample_metadata),
                (image_id_2, self.sample_metadata),
            ],
        )

        self.create_image_dir(image_id_3)
        self.assertEqual(
            list_metadatas(),
            [
                (image_id_1, self.sample_metadata),
                (image_id_2, self.sample_metadata),
                (image_id_3, self.sample_metadata),
            ],
        )

    def test_add_ref(self):
        path1 = images.get_image_repo_path() / 'some-path-1'
        path2 = images.get_image_repo_path() / 'some-path-2'

        with self.assertRaisesRegex(AssertionError, r'expect.*is_file'):
            images.add_ref(self.sample_image_id, path1)

        self.assertEqual(images.get_ref_count(self.sample_image_dir_path), 0)

        self.create_image_dir(self.sample_image_id)
        self.assertEqual(images.get_ref_count(self.sample_image_dir_path), 1)

        self.assertFalse(path1.exists())
        images.add_ref(self.sample_image_id, path1)
        self.assertTrue(path1.exists())
        self.assertEqual(images.get_ref_count(self.sample_image_dir_path), 2)

        self.assertFalse(path2.exists())
        images.add_ref(self.sample_image_id, path2)
        self.assertTrue(path2.exists())
        self.assertEqual(images.get_ref_count(self.sample_image_dir_path), 3)

        path1.unlink()
        self.assertEqual(images.get_ref_count(self.sample_image_dir_path), 2)

        path2.unlink()
        self.assertEqual(images.get_ref_count(self.sample_image_dir_path), 1)

    def test_touch(self):
        with self.assertRaisesRegex(AssertionError, r'expect.*is_file'):
            images.touch_image_dir(self.sample_image_dir_path)
        with self.assertRaises(FileNotFoundError):
            images.get_last_updated(self.sample_image_dir_path)
        self.create_image_dir(self.sample_image_id)
        t1 = images.get_last_updated(self.sample_image_dir_path)
        time.sleep(0.01)
        images.touch_image_dir(self.sample_image_dir_path)
        t2 = images.get_last_updated(self.sample_image_dir_path)
        self.assertLess(t1, t2)

    #
    # Tags.
    #

    def test_get_image_dir_path_from_tag(self):
        tag_path = images.get_tag_path('some-tag')
        with self.assertRaisesRegex(AssertionError, r'expect.*is_symlink'):
            images.get_image_dir_path_from_tag(tag_path)
        tag_path.symlink_to(images.get_tag_target(self.sample_image_dir_path))
        self.assertEqual(
            images.get_image_dir_path_from_tag(tag_path),
            self.sample_image_dir_path,
        )

    def test_find_tag_paths(self):

        def find_tag_paths():
            paths = images.find_tag_paths(self.sample_image_dir_path)
            return sorted(p.name for p in paths)

        tag_path_1 = images.get_tag_path('some-tag-1')
        tag_path_2 = images.get_tag_path('some-tag-2')

        self.assertEqual(find_tag_paths(), [])
        self.assertEqual(
            find_tag_paths(),
            images.find_tags(self.sample_image_id),
        )

        tag_path_1.symlink_to(
            images.get_tag_target(self.sample_image_dir_path)
        )
        self.assertEqual(find_tag_paths(), ['some-tag-1'])
        self.assertEqual(
            find_tag_paths(),
            images.find_tags(self.sample_image_id),
        )

        tag_path_2.symlink_to(
            images.get_tag_target(self.sample_image_dir_path)
        )
        self.assertEqual(find_tag_paths(), ['some-tag-1', 'some-tag-2'])
        self.assertEqual(
            find_tag_paths(),
            images.find_tags(self.sample_image_id),
        )


if __name__ == '__main__':
    unittest.main()
