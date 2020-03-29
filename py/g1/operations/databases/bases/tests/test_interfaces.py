import unittest

from g1.operations.databases.bases import interfaces


class InterfacesTest(unittest.TestCase):

    def test_next_key(self):
        self.assertEqual(interfaces.next_key(b'\x00'), b'\x01')
        self.assertEqual(interfaces.next_key(b'\x01'), b'\x02')
        self.assertEqual(interfaces.next_key(b'\xfe'), b'\xff')
        self.assertEqual(interfaces.next_key(b'\xff'), b'\x01\x00')
        self.assertEqual(interfaces.next_key(b'\x01\x00'), b'\x01\x01')
        self.assertEqual(interfaces.next_key(b'\x01\xfe'), b'\x01\xff')
        self.assertEqual(interfaces.next_key(b'\x01\xff'), b'\x02\x00')
        self.assertEqual(interfaces.next_key(b'\xff\xff'), b'\x01\x00\x00')
        self.assertEqual(
            interfaces.next_key(b'\x01\x00\x00\xff'), b'\x01\x00\x01\x00'
        )


if __name__ == '__main__':
    unittest.main()
