import unittest

import dataclasses
import tempfile
import typing
from pathlib import Path

from g1.texts import jsons

try:
    from g1.texts import yamls
except ImportError:
    yamls = None


@dataclasses.dataclass(frozen=True)
class TestData:
    s: str
    l: typing.List[int]


class DataclassesTest(unittest.TestCase):

    def test_jsons(self):
        self.do_test(jsons.load_dataobject, jsons.dump_dataobject)

    @unittest.skipUnless(yamls, 'PyYAML unavailable')
    def test_yamls(self):
        self.do_test(yamls.load_dataobject, yamls.dump_dataobject)

    def do_test(self, load, dump):
        expect = TestData(s='s', l=[1, 2, 3])
        with tempfile.NamedTemporaryFile() as test_tempfile:
            path = Path(test_tempfile.name)
            dump(expect, path)
            self.assertEqual(load(TestData, path), expect)


if __name__ == '__main__':
    unittest.main()
