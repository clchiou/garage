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
        bind,
        make_fqname_tuple,
        vars_as_namespace,
        _get_name,
        _is_method_overridden,
    )


@unittest.skipUnless(startup_available, 'startup unavailable')
class ComponentsTest(unittest.TestCase):

    def test_get_name(self):
        self.assertEqual('hello', _get_name('hello'))
        self.assertEqual('hello', _get_name('a.b.c.d:hello'))

    def test_make_fqname_tuple(self):
        self.assertTupleEqual((), make_fqname_tuple('a.b.c'))
        fqnames = make_fqname_tuple('a.b.c', ['x'], 'y', 'd.e.f:z')
        self.assertTupleEqual(('a.b.c:x', 'a.b.c:y', 'd.e.f:z'), fqnames)
        self.assertEqual('a.b.c:x', fqnames.x)
        self.assertEqual('a.b.c:y', fqnames.y)
        self.assertEqual('d.e.f:z', fqnames.z)
        self.assertTrue(fqnames.x.is_aggregation)
        self.assertFalse(fqnames.y.is_aggregation)

    def test_is_method_overridden(self):
        class Base:
            def meth1(self): pass
            def meth2(self): pass

        class Ext(Base):
            def meth1(self): pass
        self.assertTrue(_is_method_overridden(Ext, Base, 'meth1'))
        self.assertFalse(_is_method_overridden(Ext, Base, 'meth2'))
        self.assertTrue(_is_method_overridden(Ext(), Base, 'meth1'))
        self.assertFalse(_is_method_overridden(Ext(), Base, 'meth2'))

        class Ext(Base):
            @staticmethod
            def meth1(): pass
            @classmethod
            def meth2(cls): pass
        self.assertTrue(_is_method_overridden(Ext, Base, 'meth1'))
        self.assertTrue(_is_method_overridden(Ext, Base, 'meth2'))
        self.assertTrue(_is_method_overridden(Ext(), Base, 'meth1'))
        self.assertTrue(_is_method_overridden(Ext(), Base, 'meth2'))

    def test_empty_component(self):
        startup = Startup()
        bind(Component(), startup)
        self.assertDictEqual({}, startup.call())

        class A(Component): pass
        startup = Startup()
        bind(A(), startup)
        bind(A, startup)
        self.assertDictEqual({}, startup.call())

    def test_component(self):
        class A(Component):
            provide = ':A'
            def make(self, require):
                return 'a'

        class B(Component):
            require = ':A'
            provide = ':B'
            def make(self, require):
                return require.A

        startup = Startup()
        bind(A(), startup)
        bind(B(), startup)
        startup.set(ARGS, None)
        startup.set(CHECK_ARGS, None)
        startup.set(PARSER, None)
        self.assertDictEqual(
            {':A': 'a', ':B': 'a',
             ARGS: None, CHECK_ARGS: None, PARSER: None},
            startup.call(),
        )

    def test_bind(self):

        class A(Component):
            require = make_fqname_tuple('', ['a'])
            provide = ':as'
            def make(self, require):
                return require.a

        class B(Component):
            provide = A.require.a
            def __init__(self, msg):
                self.msg = msg
            def make(self, require):
                return self.msg

        startup = Startup()
        bind(A(), startup)
        bind(B('x'), startup)
        bind(B('y'), startup)
        startup.set(ARGS, None)
        startup.set(CHECK_ARGS, None)
        startup.set(PARSER, None)
        self.assertDictEqual(
            {':a': 'y', ':as': ['x', 'y'],
             ARGS: None, CHECK_ARGS: None, PARSER: None},
            startup.call(),
        )

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

        def parse_argv(_: PARSE) -> ARGS:
            pass

        def check_args(_: ARGS) -> CHECK_ARGS:
            pass

        startup = Startup()
        bind(A(), startup)
        bind(B(), startup)
        bind(C(), startup)
        startup.set(PARSER, None)
        startup(check_args)
        startup(parse_argv)
        startup.call()
        self.assertEqual(
            ['C.add_arguments', 'B.check_arguments', 'A.make'],
            order,
        )

    def test_vars_as_namespace(self):
        varz = vars_as_namespace({'a': 1, 'x.y.z:b': 2})
        self.assertEqual(1, varz.a)
        self.assertEqual(2, varz.b)
        with self.assertRaises(AttributeError):
            varz.c

        with self.assertRaises(ValueError):
            varz = vars_as_namespace({'a': 1, 'x.y.z:a': 2})

        varz = vars_as_namespace(
            {'a': 1, 'x.y.z:a': 2},
            aliases={'x.y.z:a': 'b'},
        )
        self.assertEqual(1, varz.a)
        self.assertEqual(2, varz.b)
        with self.assertRaises(AttributeError):
            varz.c


if __name__ == '__main__':
    unittest.main()
