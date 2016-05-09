import unittest

from pathlib import Path

import foreman
from foreman import Label, Loader, Searcher


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


class LoaderTest(unittest.TestCase):

    def test_loader(self):
        testdata = Path(__file__).parent / 'testdata'
        self.assertTrue(testdata.is_dir())

        search = Searcher([testdata / 'path2', testdata / 'path1'])
        loader = Loader(search)

        loader, foreman.LOADER = foreman.LOADER, loader
        try:
            foreman.LOADER.load_build_files(['//pkg1/pkg2:rule_x'])
        finally:
            loader, foreman.LOADER = foreman.LOADER, loader

        self.assertEqual(
            {Label.parse('//pkg1/pkg2:par_x')}, set(loader.parameters))
        self.assertEqual(
            {Label.parse('//pkg1:pkg1'),
             Label.parse('//pkg1:pkg2'),
             Label.parse('//pkg1/pkg2:rule_x'),
             Label.parse('//pkg3:rule_y'),
             Label.parse('//pkg4:pkg4')},
            set(loader.rules))

        # Reverse dependency.
        rule = loader.rules[Label.parse('//pkg1:pkg2')]
        self.assertEqual(
            {Label.parse('//pkg1:pkg1')},
            set(r.label for r in rule.all_dependencies),
        )
        rule = loader.rules[Label.parse('//pkg4:pkg4')]
        self.assertEqual(
            {Label.parse('//pkg1:pkg1')},
            set(r.label for r in rule.all_dependencies),
        )

        # Verify dependency.
        rule = loader.rules[Label.parse('//pkg1/pkg2:rule_x')]
        self.assertEqual(
            {Label.parse('//pkg1:pkg1')},
            set(r.label for r in rule.all_dependencies),
        )


if __name__ == '__main__':
    unittest.main()
