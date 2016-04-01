import unittest

from collections import OrderedDict
from datetime import datetime

from garage.timezones import TimeZone

from garage import tagged_data


class SqlUtilsTest(unittest.TestCase):

    def test_serialize(self):
        dt0 = datetime(2000, 1, 2, 3, 4, 5, 0)
        dt1 = datetime(2000, 1, 2, 3, 4, 5, 6)
        utc0 = datetime(2000, 1, 2, 3, 4, 5, 0, TimeZone.UTC)
        utc1 = datetime(2000, 1, 2, 3, 4, 5, 6, TimeZone.UTC)
        cst = utc0.astimezone(TimeZone.CST)

        for data in (101, 'a string', dt0, dt1, utc0, utc1, cst):
            self.assertEqual(
                data, tagged_data.loads(tagged_data.dumps(data)))

        self.assertEqual(
            (),
            tagged_data.loads(tagged_data.dumps([])),
        )
        self.assertEqual(
            (1,),
            tagged_data.loads(tagged_data.dumps([1])),
        )
        self.assertEqual(
            (1, 'hello'),
            tagged_data.loads(tagged_data.dumps([1, 'hello'])),
        )
        self.assertEqual(
            (1, 'hello', dt0),
            tagged_data.loads(tagged_data.dumps([1, 'hello', dt0])),
        )

        self.assertEqual(
            frozenset(),
            tagged_data.loads(tagged_data.dumps(set())),
        )
        self.assertEqual(
            frozenset((1,)),
            tagged_data.loads(tagged_data.dumps({1})),
        )
        self.assertEqual(
            frozenset((1, 'hello')),
            tagged_data.loads(tagged_data.dumps({1, 'hello'})),
        )
        self.assertEqual(
            frozenset((1, 'hello', dt0)),
            tagged_data.loads(tagged_data.dumps({1, 'hello', dt0})),
        )

        self.assertEqual(
            OrderedDict(),
            tagged_data.loads(tagged_data.dumps({})),
        )
        self.assertEqual(
            OrderedDict([(1, 'hello')]),
            tagged_data.loads(tagged_data.dumps({1: 'hello'})),
        )
        self.assertDictEqual(
            {1: 'hello', dt0: dt1},
            dict(tagged_data.loads(tagged_data.dumps({
                1: 'hello',
                dt0: dt1,
            }))),
        )


if __name__ == '__main__':
    unittest.main()
