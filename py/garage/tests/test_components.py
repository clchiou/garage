import unittest

from tests.availability import startup_available

if startup_available:
    from startup import Startup
    from garage.components import (
        ARGS,
        CHECK_ARGS,
        PARSE,
        PARSER,
        Component,
        Fqname,
        bind,
        make_fqname_tuple,
        vars_as_namespace,
    )


@unittest.skipUnless(startup_available, 'startup unavailable')
class ComponentsTest(unittest.TestCase):

    def test_fqname_parse(self):
        with self.assertRaises(ValueError):
            Fqname.parse('hello')
        self.assertEqual('hello', Fqname.parse('a.b.c.d:hello').name)

    def test_make_fqname_tuple(self):

        self.assertTupleEqual((), make_fqname_tuple('a.b.c'))

        fqnames = make_fqname_tuple(
            'a.b.c',
            ['x'], 'y', Fqname.parse('d.e.f:z'),
        )
        self.assertTupleEqual(('a.b.c:x', 'a.b.c:y', 'd.e.f:z'), fqnames)
        self.assertEqual('a.b.c:x', fqnames.x)
        self.assertEqual('a.b.c:y', fqnames.y)
        self.assertEqual('d.e.f:z', fqnames.z)
        self.assertEqual(['a.b.c:x'], fqnames.x.as_annotation())
        self.assertEqual('a.b.c:y', fqnames.y.as_annotation())

    # startup.call()'s output when all component's provide are empty
    BASE_VARS = {ARGS: None, CHECK_ARGS: None, PARSE: None, PARSER: None}

    def _call_startup(self, startup):

        @startup
        def parse_argv(_: PARSE) -> ARGS:
            pass

        startup.set(PARSER, None)

        return startup.call()

    def test_empty_component(self):
        startup = Startup()
        bind(Component(), startup)
        self.assertDictEqual(self.BASE_VARS, self._call_startup(startup))

        class A(Component): pass
        startup = Startup()
        bind(A(), startup)
        bind(A, startup)
        self.assertDictEqual(self.BASE_VARS, self._call_startup(startup))

    def test_component(self):
        class A(Component):
            provide = make_fqname_tuple('hello', 'a')
            def make(self, require):
                return 'str_a'

        class B(Component):
            require = (A.provide.a,)
            provide = make_fqname_tuple('hello', 'b')
            def make(self, require):
                return require.a + 'a'

        startup = Startup()
        bind(A(), startup)
        bind(B(), startup)

        expect = dict(self.BASE_VARS)
        expect.update({
            'hello:a': 'str_a',
            'hello:b': 'str_aa',
        })
        self.assertDictEqual(expect, self._call_startup(startup))

    def test_order(self):

        call_order = []

        class A(Component):

            def __init__(self, order):
                self.order = order

            def add_arguments(self, parser):
                call_order.append(('add_arguments', self.order))

            def check_arguments(self, parser, args):
                call_order.append(('check_arguments', self.order))

            def make(self, require):
                call_order.append(('make', self.order))

        startup = Startup()
        bind(A('3'), startup)
        bind(A('1'), startup)
        bind(A('2'), startup)

        self._call_startup(startup)

        self.assertEqual(
            [
                ('add_arguments', '1'),
                ('add_arguments', '2'),
                ('add_arguments', '3'),
                ('check_arguments', '1'),
                ('check_arguments', '2'),
                ('check_arguments', '3'),
                ('make', '1'),
                ('make', '2'),
                ('make', '3'),
            ],
            call_order,
        )

    def test_component_read_all(self):

        class A(Component):
            provide = make_fqname_tuple('hello', 'a')
            def __init__(self, msg):
                self.msg = msg
            def make(self, require):
                return self.msg

        class B(Component):
            require = (A.provide.a.read_all(),)
            provide = make_fqname_tuple('hello', ['alist'])
            def make(self, require):
                return require.a

        startup = Startup()
        bind(A('x'), startup)
        bind(A('y'), startup)
        bind(B, startup)

        expect = dict(self.BASE_VARS)
        expect.update({
            'hello:a': 'y',
            'hello:alist': ['x', 'y'],
        })
        self.assertDictEqual(expect, self._call_startup(startup))

    def test_resolved_order(self):

        order = []

        # Component A requires and provides nothing (and it is
        # alphabetically before B and C).  We have to make sure that
        # A.make is called after B.check_argument and C.add_arguments.

        class A(Component):
            def make(self, require):
                order.append('A.make')

        class B(Component):
            def check_arguments(self, parser, args):
                order.append('B.check_arguments')

        class C(Component):
            def add_arguments(self, parser):
                order.append('C.add_arguments')

        startup = Startup()
        bind(A(), startup)
        bind(B(), startup)
        bind(C(), startup)

        self.assertDictEqual(self.BASE_VARS, self._call_startup(startup))
        self.assertEqual(
            ['C.add_arguments', 'B.check_arguments', 'A.make'],
            order,
        )

    def test_vars_as_namespace(self):
        varz = vars_as_namespace({'x.y.z:a': 1, 'x.y.z:b': 2})
        self.assertEqual(1, varz.a)
        self.assertEqual(2, varz.b)
        self.assertFalse(hasattr(varz, 'c'))
        with self.assertRaises(AttributeError):
            varz.c

        with self.assertRaisesRegex(ValueError, r'overwrite name'):
            varz = vars_as_namespace({'p.q.r:a': 1, 'x.y.z:a': 2})


if __name__ == '__main__':
    unittest.main()
