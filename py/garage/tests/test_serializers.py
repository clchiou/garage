import unittest

from garage.serializers import *


class SerializersTest(unittest.TestCase):

    def test_primitive(self):
        Int = Primitive.of_type(int)
        self.assertEqual(1, Int.lower(1))
        self.assertEqual(1, Int.higher(1))
        with self.assertRaises(ValueError):
            Int.lower('1')
        with self.assertRaises(ValueError):
            Int.higher('1')

        NNInt = Primitive(
            Primitive.predicate(lambda i: 0 <= i),
            Primitive.predicate(lambda i: 0 <= i),
        )
        self.assertEqual(0, NNInt.lower(0))
        self.assertEqual(3, NNInt.higher(3))
        with self.assertRaises(ValueError):
            NNInt.lower(-1)
        with self.assertRaises(ValueError):
            NNInt.higher(-1)

    def test_list(self):
        list_of_ints = List(Primitive.of_type(int))
        low_high = [
            ((), ()),
            ((1,), (1,)),
            ((1, 2), (1, 2)),
        ]
        for low, high in low_high:
            self.assertTupleEqual(low, list_of_ints.lower(high))
            self.assertTupleEqual(high, list_of_ints.higher(low))
        with self.assertRaises(ValueError):
            list_of_ints.lower(['1'])
        with self.assertRaises(ValueError):
            list_of_ints.higher(['1'])

    def test_set(self):
        set_of_ints = Set(Primitive.of_type(int))
        low_high = [
            ((), set()),
            ((1,), {1}),
            ((1, 2), {1, 2}),
        ]
        for low, high in low_high:
            self.assertTupleEqual(low, set_of_ints.lower(high))
            self.assertSetEqual(high, set_of_ints.higher(low))
        with self.assertRaises(ValueError):
            set_of_ints.lower({'1'})
        with self.assertRaises(ValueError):
            set_of_ints.higher(('1',))

    def test_record(self):
        record_type = Record(
            ('x', Primitive.of_type(int)),
            ('x_list', List(Primitive.of_type(int))),
            ('x_set', Set(Primitive.of_type(int))),
            Record.Optional('x_optional', Primitive.of_type(int)),
        )

        def assertRecordEqual(expect, actual):
            self.assertEqual(expect.x, actual.x)
            self.assertTupleEqual(expect.x_list, actual.x_list)
            self.assertSetEqual(expect.x_set, actual.x_set)
            self.assertEqual(expect.x_optional, actual.x_optional)

        obj = Obj(x=0, x_list=None, x_set=None, x_optional=None, extra='x')
        self.assertDictEqual({'x': 0}, record_type.lower(obj))

        obj = Obj(x=2, x_list=[], x_set=set())
        self.assertDictEqual({'x': 2}, record_type.lower(obj))

        obj = Obj(x=3)
        self.assertDictEqual({'x': 3}, record_type.lower(obj))

        obj = Obj(x=4, x_list=[5], x_optional=0)
        self.assertDictEqual(
            {'x': 4, 'x_list': (5,), 'x_optional': 0},
            record_type.lower(obj),
        )

        assertRecordEqual(
            Obj(x=101, x_list=(), x_set=frozenset(), x_optional=None),
            record_type.higher({'x': 101}),
        )

        assertRecordEqual(
            Obj(x=102,
                x_list=(103,),
                x_set=frozenset((104, 105)),
                x_optional=106,
            ),
            record_type.higher({
                'x': 102,
                'x_list': [103],
                'x_set': {104, 105},
                'x_optional': 106,
            }),
        )

        obj = Obj()
        with self.assertRaises(ValueError):
            record_type.lower(obj)

        with self.assertRaises(ValueError):
            record_type.higher({})

    def test_extra_fields(self):
        record_type = Record(
            ('x', Primitive.of_type(int)),
        )

        self.assertEqual(
            {'x': 0},
            record_type.lower(Obj(x=0, y=1, z=2)),
        )

        obj = record_type.higher({'x': 0, 'y': 1, 'z': 2})
        self.assertEqual({'x': 0}, obj._asdict())

    def test_either(self):
        either = Record(
            Record.Either(
                ('x', Primitive.of_type(int)),
                ('y', Primitive.of_type(str)),
            ),
        )

        def assertObjectEqual(expect, actual):
            self.assertEqual(expect.x, actual.x)
            self.assertEqual(expect.y, actual.y)

        self.assertEqual({'x': 1}, either.lower(Obj(x=1)))
        self.assertEqual({'y': '1'}, either.lower(Obj(y='1')))

        assertObjectEqual(Obj(x=1, y=None), either.higher({'x': 1}))
        assertObjectEqual(Obj(x=None, y='1'), either.higher({'y': '1'}))

        with self.assertRaises(ValueError):
            either.lower(Obj(x=1, y='1'))
        with self.assertRaises(ValueError):
            either.higher({'x': 1, 'y': '1'})

    def test_either_list(self):
        either = Record(
            Record.Either(
                ('x', List(Primitive.of_type(int))),
                ('y', Set(Primitive.of_type(str))),
            ),
        )

        self.assertEqual({'x': ()}, either.lower(Obj(x=[])))
        self.assertEqual({'y': ()}, either.lower(Obj(y=set())))

        with self.assertRaises(ValueError):
            either.lower(Obj())
        with self.assertRaises(ValueError):
            either.lower(Obj(x=[], y=set()))

    def test_some_list(self):
        some = Record(
            Record.AtLeastOne(
                ('x', Primitive.of_type(int)),
                ('y', Primitive.of_type(int)),
            ),
        )

        self.assertEqual({'x': 1}, some.lower(Obj(x=1)))
        self.assertEqual({'y': 2}, some.lower(Obj(y=2)))
        self.assertEqual({'x': 1, 'y': 2}, some.lower(Obj(x=1, y=2)))

        with self.assertRaises(ValueError):
            some.lower(Obj())

    def test_nested(self):
        type_ = List(List(Record(('x', Primitive.of_type(int)))))
        self.assertEqual(
            (({'x': 1}, {'x': 2}),),
            type_.lower([[Obj(x=1), Obj(x=2)]]),
        )


class Obj:

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


if __name__ == '__main__':
    unittest.main()
