import unittest

from g1.messaging import metadata


class MetadataTest(unittest.TestCase):

    def test_metadata(self):

        class Test:
            pass

        self.assertIsNone(metadata.get_metadata(Test, 'x'))
        self.assertIsNone(metadata.get_metadata(Test, 'y'))
        self.assertIsNone(getattr(Test, metadata._METADATA, None))

        metadata.set_metadata(Test, 'x', 1)
        self.assertEqual(getattr(Test, metadata._METADATA), {'x': 1})
        metadata.set_metadata(Test, 'y', 2)
        self.assertEqual(getattr(Test, metadata._METADATA), {'x': 1, 'y': 2})

        self.assertEqual(metadata.get_metadata(Test, 'x'), 1)
        self.assertEqual(metadata.get_metadata(Test, 'y'), 2)

        metadata.set_metadata(Test, 'x', 3)
        self.assertEqual(getattr(Test, metadata._METADATA), {'x': 3, 'y': 2})
        metadata.set_metadata(Test, 'y', 4)
        self.assertEqual(getattr(Test, metadata._METADATA), {'x': 3, 'y': 4})

        self.assertEqual(metadata.get_metadata(Test, 'x'), 3)
        self.assertEqual(metadata.get_metadata(Test, 'y'), 4)


if __name__ == '__main__':
    unittest.main()
