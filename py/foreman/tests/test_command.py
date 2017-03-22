import unittest

from pathlib import Path
import contextlib
import io
import json
import types

import foreman


class CommandTest(unittest.TestCase):
    """Try to simulate `foreman.py build|list` command."""

    def tearDown(self):
        foreman.LOADER = None
        if hasattr(foreman, '_test_ran'):
            del foreman._test_ran

    def test_build(self):
        args = types.SimpleNamespace(
            dry_run=False,
            parameter=(),
            rule=['//pkg1:rule1', '//pkg1/pkg2:rule2'],
        )

        testdata = Path(__file__).parent / 'testdata/test_command'
        self.assertTrue(testdata.is_dir())
        loader = foreman.Loader(foreman.Searcher([testdata]))

        foreman.LOADER = loader
        foreman.command_build(args, loader)

        self.assertTrue(foreman._test_ran)

    def test_list(self):
        args = types.SimpleNamespace(
            dry_run=False,
            parameter=(),
            rule=['//pkg1:rule1', '//pkg1/pkg2:rule2'],
        )

        testdata = Path(__file__).parent / 'testdata/test_command'
        self.assertTrue(testdata.is_dir())
        loader = foreman.Loader(foreman.Searcher([testdata]))

        f = io.StringIO()
        with contextlib.redirect_stdout(f):
            foreman.LOADER = loader
            foreman.command_list(args, loader)

        data = json.loads(f.getvalue())

        par1 = data['//pkg1']['parameters'][0]
        self.assertEqual('//pkg1:par1', par1['label'])
        self.assertEqual('pkg1', par1['default'])

        par2 = data['//pkg1/pkg2']['parameters'][0]
        self.assertEqual('//pkg1/pkg2:par2', par2['label'])
        self.assertEqual('pkg1/pkg2', par2['default'])


if __name__ == '__main__':
    unittest.main()
