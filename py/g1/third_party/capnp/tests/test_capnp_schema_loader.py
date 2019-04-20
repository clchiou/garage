import unittest

from capnp import _capnp  # pylint: disable=unused-import

try:
    from capnp import _capnp_test
except ImportError:
    _capnp_test = None

# pylint: disable=c-extension-no-member


@unittest.skipUnless(_capnp_test, '_capnp_test unavailable')
class SchemaLoaderTest(unittest.TestCase):

    def test_schema_loader(self):
        loader = _capnp.SchemaLoader()
        self.assertEqual(len(loader.getAllLoaded()), 0)
        self.assertEqual(list(loader.getAllLoaded()), [])

        node = _capnp_test.makeSchemaNode()
        schema = loader.loadOnce(node)

        schema_array = loader.getAllLoaded()
        self.assertEqual(len(schema_array), 1)
        self.assertEqual(list(loader.getAllLoaded()), [schema])
        self.assertEqual(schema_array[0], schema)

        self.assertEqual(
            loader.tryGet(0, _capnp_test.makeSchemaBrand(), schema),
            schema,
        )
        self.assertIsNone(
            loader.tryGet(1, _capnp_test.makeSchemaBrand(), schema),
        )


if __name__ == '__main__':
    unittest.main()
