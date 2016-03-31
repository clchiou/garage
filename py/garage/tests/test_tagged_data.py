import unittest

from collections import OrderedDict
from datetime import datetime

from garage.timezones import TimeZone

from garage.tagged_data import deserialize, serialize


class SqlUtilsTest(unittest.TestCase):

    def test_serialize(self):
        dt0 = datetime(2000, 1, 2, 3, 4, 5, 0)
        dt1 = datetime(2000, 1, 2, 3, 4, 5, 6)
        utc0 = datetime(2000, 1, 2, 3, 4, 5, 0, TimeZone.UTC)
        utc1 = datetime(2000, 1, 2, 3, 4, 5, 6, TimeZone.UTC)
        cst = utc0.astimezone(TimeZone.CST)

        for data in (101, 'a string', dt0, dt1, utc0, utc1, cst):
            self.assertEqual(
                data, deserialize(serialize(data)))

        self.assertEqual(
            (),
            deserialize(serialize([])),
        )
        self.assertEqual(
            (1,),
            deserialize(serialize([1])),
        )
        self.assertEqual(
            (1, 'hello'),
            deserialize(serialize([1, 'hello'])),
        )
        self.assertEqual(
            (1, 'hello', dt0),
            deserialize(serialize([1, 'hello', dt0])),
        )

        self.assertEqual(
            frozenset(),
            deserialize(serialize(set())),
        )
        self.assertEqual(
            frozenset((1,)),
            deserialize(serialize({1})),
        )
        self.assertEqual(
            frozenset((1, 'hello')),
            deserialize(serialize({1, 'hello'})),
        )
        self.assertEqual(
            frozenset((1, 'hello', dt0)),
            deserialize(serialize({1, 'hello', dt0})),
        )

        self.assertEqual(
            OrderedDict(),
            deserialize(serialize({})),
        )
        self.assertEqual(
            OrderedDict([(1, 'hello')]),
            deserialize(serialize({1: 'hello'})),
        )
        self.assertDictEqual(
            {1: 'hello', dt0: dt1},
            dict(deserialize(serialize({
                1: 'hello',
                dt0: dt1,
            }))),
        )


if __name__ == '__main__':
    unittest.main()
