import unittest

import contextlib

import v8


class UndefinedTest(unittest.TestCase):

    def test_undefined(self):
        self.assertIsInstance(v8.UNDEFINED, v8.UndefinedType)
        self.assertFalse(v8.UNDEFINED)
        # It is a singleton.
        self.assertIs(v8.UNDEFINED, v8.UndefinedType())


class ValueTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.assertEqual(v8.Isolate.num_alive, 0)
        self.stack = contextlib.ExitStack()
        self.stack.__enter__()
        self.isolate = self.stack.enter_context(v8.Isolate())
        self.assertEqual(v8.Isolate.num_alive, 1)
        self.stack.enter_context(self.isolate.scope())
        self.stack.enter_context(v8.HandleScope(self.isolate))
        self.context = self.stack.enter_context(v8.Context(self.isolate))

    def tearDown(self):
        self.stack.close()
        self.assertEqual(v8.Isolate.num_alive, 0)
        super().tearDown()

    def test_primitive_values_from_python(self):
        self.context['u'] = v8.UNDEFINED
        self.context['n'] = None
        self.context['b1'] = True
        self.context['b2'] = False
        self.context['i'] = 1
        self.context['f'] = 0.5
        self.context['s'] = 'foo bar'

        self.assertTrue(v8.run(self.context, 'typeof u === "undefined"'))
        self.assertTrue(v8.run(self.context, 'n === null'))
        self.assertTrue(v8.run(self.context, 'b1 === true'))
        self.assertTrue(v8.run(self.context, 'b2 === false'))
        self.assertTrue(v8.run(self.context, 'i === 1'))
        self.assertTrue(v8.run(self.context, 'f === 0.5'))
        self.assertTrue(v8.run(self.context, 's === "foo bar"'))

        self.context['int32_min'] = -2**31
        self.context['int32_min_minus_1'] = -2**31 - 1
        self.assertTrue(v8.run(self.context, 'int32_min === -2147483648'))
        self.assertTrue(
            v8.run(self.context, 'int32_min_minus_1 === -2147483649n')
        )

        self.context['uint32_max'] = 2**32 - 1
        self.context['uint32_max_plus_1'] = 2**32
        self.assertTrue(v8.run(self.context, 'uint32_max === 4294967295'))
        self.assertTrue(
            v8.run(self.context, 'uint32_max_plus_1 === 4294967296n')
        )

        self.context['int64_min'] = -2**63
        self.assertTrue(
            v8.run(self.context, 'int64_min === -9223372036854775808n')
        )
        with self.assertRaisesRegex(OverflowError, r'int too big to convert'):
            self.context['int64_min_minux_1'] = -2**63 - 1

        self.context['int64_max'] = 2**63 - 1
        self.assertTrue(
            v8.run(self.context, 'int64_max === 9223372036854775807n')
        )
        with self.assertRaisesRegex(OverflowError, r'int too big to convert'):
            self.context['int64_max_plus_1'] = 2**63

        with self.assertRaisesRegex(
            TypeError,
            r'to-JavaScript conversion is unsupported: ',
        ):
            self.context['x'] = {'x': 1}

    def test_primitive_values_to_python(self):
        v8.run(
            self.context,
            '''
            u = undefined;
            n = null;
            b1 = true;
            b2 = false;
            i = 1;
            f = 0.5;
            s = 'foo bar';

            int32_min = -2147483648;
            int32_min_minus_1 = -2147483649;
            int32_min_minus_1_bigint = -2147483649n;

            uint32_max = 4294967295;
            uint32_max_plus_1 = 4294967296;
            uint32_max_plus_1_bigint = 4294967296n;

            int64_min = -9223372036854775808n;
            int64_min_minus_1 = -9223372036854775809n;

            int64_max = 9223372036854775807n;
            int64_max_plus_1 = 9223372036854775808n;

            null;
            ''',
        )

        self.assertIs(self.context['u'], v8.UNDEFINED)
        self.assertIsNone(self.context['n'])
        self.assertIs(self.context['b1'], True)
        self.assertIs(self.context['b2'], False)
        self.assertIsInstance(self.context['i'], int)
        self.assertEqual(self.context['i'], 1)
        self.assertIsInstance(self.context['f'], float)
        self.assertEqual(self.context['f'], 0.5)
        self.assertIsInstance(self.context['s'], str)
        self.assertEqual(self.context['s'], 'foo bar')

        self.assertIsInstance(self.context['int32_min'], int)
        self.assertEqual(self.context['int32_min'], -2**31)
        self.assertIsInstance(self.context['int32_min_minus_1'], float)
        self.assertEqual(self.context['int32_min_minus_1'], -2**31 - 1)
        self.assertIsInstance(self.context['int32_min_minus_1_bigint'], int)
        self.assertEqual(self.context['int32_min_minus_1_bigint'], -2**31 - 1)

        self.assertIsInstance(self.context['uint32_max'], int)
        self.assertEqual(self.context['uint32_max'], 2**32 - 1)
        self.assertIsInstance(self.context['uint32_max_plus_1'], float)
        self.assertEqual(self.context['uint32_max_plus_1'], 2**32)
        self.assertIsInstance(self.context['uint32_max_plus_1_bigint'], int)
        self.assertEqual(self.context['uint32_max_plus_1_bigint'], 2**32)

        self.assertIsInstance(self.context['int64_min'], int)
        self.assertEqual(self.context['int64_min'], -2**63)
        with self.assertRaisesRegex(
            ValueError,
            r'unable to convert value to target type',
        ):
            # pylint: disable=pointless-statement
            self.context['int64_min_minus_1']

        self.assertIsInstance(self.context['int64_max'], int)
        self.assertEqual(self.context['int64_max'], 2**63 - 1)
        with self.assertRaisesRegex(
            ValueError,
            r'unable to convert value to target type',
        ):
            # pylint: disable=pointless-statement
            self.context['int64_max_plus_1']

    def test_container_constructor(self):
        self.context['d'] = v8.Object(self.context)
        self.assertEqual(list(self.context['d']), [])

        self.context['d']['a'] = v8.Array(self.context)
        self.assertEqual(list(self.context['d']), ['a'])
        self.assertEqual(len(self.context['d']['a']), 0)

        self.context['d']['a'].append(v8.Object(self.context))
        self.assertEqual(list(self.context['d']), ['a'])
        self.assertEqual(len(self.context['d']['a']), 1)
        self.assertEqual(list(self.context['d']['a'][0]), [])

    def test_nested_container(self):
        d = v8.run(
            self.context,
            '''
            d = {k1: [1, 'x', [2, {k2: [3]}], 4]};
            ''',
        )
        self.assertIsInstance(d, v8.Object)
        self.assertIsInstance(d['k1'], v8.Array)
        self.assertIsInstance(d['k1'][2], v8.Array)
        self.assertIsInstance(d['k1'][2][1], v8.Object)
        self.assertIsInstance(d['k1'][2][1]['k2'], v8.Array)
        self.assertEqual(d['k1'][2][1]['k2'][0], 3)

    def test_array(self):
        a = v8.run(self.context, 'a = [1, "x", true];')

        self.assertEqual(len(a), 3)

        self.assertEqual(list(a), [1, 'x', True])

        self.assertIn(1, a)
        self.assertIn('x', a)
        self.assertIn(True, a)
        self.assertNotIn(False, a)

        self.assertEqual(a[0], 1)
        self.assertEqual(a[1], 'x')
        self.assertEqual(a[2], True)

        a[0] = 99
        a[2] = None
        self.assertEqual(list(a), [99, 'x', None])

        with self.assertRaisesRegex(
            OverflowError,
            r'can\'t convert negative value to unsigned int',
        ):
            # pylint: disable=pointless-statement
            a[-1]
        with self.assertRaisesRegex(
            OverflowError,
            r'can\'t convert negative value to unsigned int',
        ):
            a[-1] = 1

        with self.assertRaisesRegex(
            IndexError,
            r'expect array index 0 <= x < 3, not 3',
        ):
            # pylint: disable=pointless-statement
            a[3]
        with self.assertRaisesRegex(
            IndexError,
            r'expect array index 0 <= x < 3, not 3',
        ):
            a[3] = 1

        a.append(100)
        a.append(101)
        a.append(102)
        self.assertEqual(list(a), [99, 'x', None, 100, 101, 102])

    def test_object(self):
        o = v8.run(self.context, 'o = {p: 1, q: null};')

        self.assertEqual(len(o), 2)

        self.assertEqual(list(o), ['p', 'q'])

        self.assertIn('p', o)
        self.assertIn('q', o)
        self.assertNotIn('r', o)

        self.assertEqual(o['p'], 1)
        self.assertIsNone(o['q'])

        o['p'] = 'spam egg'
        self.assertEqual(o['p'], 'spam egg')

        with self.assertRaisesRegex(KeyError, r'\'r\''):
            # pylint: disable=pointless-statement
            o['r']

        o['r'] = 'foo bar'
        self.assertEqual(list(o), ['p', 'q', 'r'])
        self.assertIn('r', o)
        self.assertEqual(o['r'], 'foo bar')

    def test_self_reference(self):
        x = v8.Object(self.context)
        self.context['x'] = x
        self.context['x']['x'] = x
        self.assertTrue(v8.run(self.context, 'x.x === x;'))
        self.assertTrue(v8.run(self.context, 'x.x.x === x;'))

    def test_type_predicates(self):
        predicates = [name for name in dir(v8.Value) if name.startswith('is_')]
        self.assertEqual(len(predicates), 55)

        def assert_predicates(x, expect_true):
            for name in predicates:
                if name in expect_true:
                    self.assertTrue(
                        getattr(x, name)(),
                        'expect %s be true on %r' % (name, x),
                    )
                else:
                    self.assertFalse(
                        getattr(x, name)(),
                        'expect %s be false on %r' % (name, x),
                    )

        v8.run(
            self.context,
            '''
            symbol = Symbol();
            function func() {}
            array = [];
            object = {};
            date = new Date();
            reg_exp = /x/;
            ''',
        )

        assert_predicates(self.context['symbol'], {'is_name', 'is_symbol'})
        assert_predicates(self.context['func'], {'is_function', 'is_object'})
        assert_predicates(self.context['array'], {'is_array', 'is_object'})
        assert_predicates(self.context['date'], {'is_date', 'is_object'})
        assert_predicates(self.context['reg_exp'], {'is_reg_exp', 'is_object'})

    def test_from_python(self):
        self.context['d'] = v8.from_python(
            self.context,
            {
                'u': v8.UNDEFINED,
                'n': None,
                'b1': True,
                'b2': False,
                'i': 1,
                'f': 0.5,
                's': 'foo bar',
                'l': [{
                    'k': [2]
                }],
                'd': {
                    'k1': [{
                        'k2': 3
                    }]
                },
            },
        )

        self.assertTrue(v8.run(self.context, 'typeof d.u === "undefined";'))
        self.assertTrue(v8.run(self.context, 'd.n === null;'))
        self.assertTrue(v8.run(self.context, 'd.b1 === true;'))
        self.assertTrue(v8.run(self.context, 'd.b2 === false;'))
        self.assertTrue(v8.run(self.context, 'd.i === 1;'))
        self.assertTrue(v8.run(self.context, 'd.f === 0.5;'))
        self.assertTrue(v8.run(self.context, 'd.s === "foo bar";'))

        self.assertTrue(v8.run(self.context, 'd.l.length === 1;'))
        self.assertTrue(v8.run(self.context, 'd.l[0].k.length === 1;'))
        self.assertTrue(v8.run(self.context, 'd.l[0].k[0] === 2;'))

        self.assertTrue(v8.run(self.context, 'd.d.hasOwnProperty("k1");'))
        self.assertTrue(v8.run(self.context, 'd.d.k1.length === 1;'))
        self.assertTrue(v8.run(self.context, 'd.d.k1[0].k2 === 3;'))

        with self.assertRaisesRegex(TypeError, r'expect str key: ()'):
            v8.from_python(self.context, {(): 1})

        with self.assertRaisesRegex(
            TypeError,
            r'unsupported type: <object .*>',
        ):
            v8.from_python(self.context, object())

    def test_to_python(self):
        self.assertEqual(
            v8.to_python(
                v8.run(
                    self.context,
                    '''
                    d = {
                        u: undefined,
                        n: null,
                        b1: true,
                        b2: false,
                        i: 1,
                        f: 0.5,
                        s: 'foo bar',
                        a: [2, true, 'spam egg', {k: 1}],
                        d: {k1: [{k2: []}]},
                    };
                    ''',
                )
            ),
            {
                'u': None,
                'n': None,
                'b1': True,
                'b2': False,
                'i': 1,
                'f': 0.5,
                's': 'foo bar',
                'a': [2, True, 'spam egg', {
                    'k': 1
                }],
                'd': {
                    'k1': [{
                        'k2': []
                    }]
                },
            },
        )

        self.assertEqual(
            v8.to_python(v8.run(self.context, '[{k: undefined}]')),
            [{
                'k': None
            }],
        )
        self.assertEqual(
            v8.to_python(
                v8.run(self.context, '[{k: undefined}]'),
                undefined_to_none=False,
            ),
            [{
                'k': v8.UNDEFINED
            }],
        )

        v8.run(self.context, 'd = {a: [1, 2, 3]};')
        d = v8.to_python(self.context['d'], sequence_type=tuple)
        self.assertIsInstance(d['a'], tuple)
        self.assertEqual(d['a'], (1, 2, 3))

        with self.assertRaisesRegex(
            TypeError,
            r'unsupported type: <v8._v8.Value object Symbol\(\)>',
        ):
            v8.to_python(v8.run(self.context, 'Symbol();'))


if __name__ == '__main__':
    unittest.main()
