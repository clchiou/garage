import unittest

import datetime
import json

from garage.collections import make_sorted_ordered_dict
from garage.json import encode_datetime
from garage.json import encode_mapping
from garage.json import join_encoders
from garage.timezones import TimeZone


class JsonTest(unittest.TestCase):

    def test_encoders(self):
        dt = datetime.datetime(2000, 1, 2, 3, 4, 5, 6, TimeZone.UTC)
        dt_json = '"2000-01-02T03:04:05.000006+00:00"'

        mapping = make_sorted_ordered_dict(c=3, a=1, b=2)
        mapping_json = '{"a": 1, "b": 2, "c": 3}'

        with self.assertRaises(TypeError):
            json.dumps(dt)

        self.assertEqual(
            dt_json,
            json.dumps(dt, default=encode_datetime),
        )

        self.assertEqual(
            dt_json,
            json.dumps(
                dt, default=join_encoders(encode_mapping, encode_datetime)
            ),
        )

        self.assertEqual(
            mapping_json,
            json.dumps(mapping, default=encode_mapping),
        )

        self.assertEqual(
            mapping_json,
            json.dumps(
                mapping, default=join_encoders(encode_datetime, encode_mapping)
            ),
        )


if __name__ == '__main__':
    unittest.main()
