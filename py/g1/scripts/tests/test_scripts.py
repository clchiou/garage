import unittest

import g1.scripts.bases
import g1.scripts.commands
import g1.scripts.utils
from g1 import scripts


class ExportTest(unittest.TestCase):

    def test_export_names(self):
        self.assertNotIn('bases', scripts.__all__)
        self.assertNotIn('commands', scripts.__all__)
        self.assertNotIn('utils', scripts.__all__)
        s1 = set(g1.scripts.bases.__all__)
        s2 = set(g1.scripts.commands.__all__)
        s3 = set(g1.scripts.utils.__all__)
        self.assertFalse(s1 & s2)
        self.assertFalse(s1 & s3)
        self.assertFalse(s2 & s3)


if __name__ == '__main__':
    unittest.main()
