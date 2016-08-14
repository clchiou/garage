import unittest

from argparse import Namespace
from pathlib import Path

import foreman
from foreman import Label, Loader, Searcher


class ConfigsTest(unittest.TestCase):

    def test_configs(self):
        testdata = Path(__file__).parent / 'testdata'
        self.assertTrue(testdata.is_dir())

        search = Searcher([testdata / 'path2', testdata / 'path1'])
        loader = Loader(search)

        args = Namespace(
            dry_run=False,
            parameter=None,
            rule=['//pkg-configs:rule-A'],
        )

        loader, foreman.LOADER = foreman.LOADER, loader
        try:
            self.assertEqual(0, foreman.command_build(args, foreman.LOADER))
        finally:
            loader, foreman.LOADER = foreman.LOADER, loader

        label = Label.parse('//pkg-configs:executed_rules')
        executed_rules = loader.parameters[label].default

        expect = [
            ('rule-A', {0}),
            ('rule-B', {1}),
            ('rule-C', {2}),
            ('rule-D', {1, 2}),
            ('rule-E', {1}),
            ('rule-F', {2}),
        ]
        for rule_name, xs in expect:
            self.assertEqual(
                xs,
                {ps['x'] for name, ps in executed_rules if name == rule_name},
            )


if __name__ == '__main__':
    unittest.main()
