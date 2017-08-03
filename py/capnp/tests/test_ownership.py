import unittest

import weakref

import capnp

from tests.fixtures import Fixture


class DynamicsTest(Fixture):

    def setUp(self):
        self.loader = capnp.SchemaLoader()
        self.loader.open()
        self.loader.load_bytes(self.compile('test-1.capnp'))
        self.struct_schema = \
            self.loader.get_schema('unittest.test_1:SomeStruct')
        self.enum_schema = self.loader.get_schema('unittest.test_1:SomeEnum')

    def tearDown(self):
        self.loader.close()

    def test_ownership(self):

        result = []

        obj = capnp.DynamicObject._make(
            capnp.MessageBuilder(),
            self.struct_schema,
        )
        obj._struct.init('s1').init('s2').init('s3')['i32'] = 42

        obj_id = id(obj)
        weakref.finalize(obj, result.append, obj_id)

        s1 = obj.s1
        s1_str = str(s1)

        o2 = obj._as_reader()
        o2_str = str(o2)

        self.assertIs(s1._root, obj)
        self.assertIs(s1.s2._root, obj)
        self.assertIs(s1.s2.s3._root, obj)

        self.assertIs(o2._root, obj)
        self.assertIs(o2.s1._root, obj)
        self.assertIs(o2.s1.s2._root, obj)
        self.assertIs(o2.s1.s2.s3._root, obj)

        obj = None

        self.assertEqual(s1_str, str(s1))
        self.assertEqual(o2_str, str(o2))

        self.assertEqual([], result)

        s1 = None
        o2 = None

        self.assertEqual([obj_id], result)


if __name__ == '__main__':
    unittest.main()
