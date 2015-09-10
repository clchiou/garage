import unittest

import json

from garage.collections import ImmutableSortedDict
from garage.json import encode_mapping


class JsonTest(unittest.TestCase):

    def test_okay(self):
        with self.assertRaises(TypeError):
            json.dumps(ImmutableSortedDict(c=3, a=1, b=2))

        self.assertEqual(
            '''{"a": 1, "b": 2, "c": 3}''',
            json.dumps(ImmutableSortedDict(c=3, a=1, b=2),
                       default=encode_mapping),
        )


if __name__ == '__main__':
    unittest.main()
