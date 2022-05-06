import unittest
import unittest.mock

from g1.backgrounds import consoles


class ConsolesTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.mock_sock = unittest.mock.Mock(spec_set=['send', 'recv'])
        self.console = consoles.SocketConsole(self.mock_sock)

    def assert_buffer(self, buffer, lines):
        self.assertEqual(self.console._SocketConsole__buffer, buffer)
        self.assertEqual(self.console._SocketConsole__lines, lines)

    def test_raw_input_one_byte_per_chunk(self):
        data = b'hello\r\nworld\n\r\n\n\nfoobar'
        self.mock_sock.recv.side_effect = (
            [data[i:i + 1] for i in range(len(data))] + [b'']
        )
        self.assert_buffer([], [])

        self.assertEqual(self.console.raw_input(), 'hello')
        self.assert_buffer([], [])

        self.assertEqual(self.console.raw_input(), 'world')
        self.assert_buffer([], [])

        self.assertEqual(self.console.raw_input(), '')
        self.assert_buffer([], [])

        self.assertEqual(self.console.raw_input(), '')
        self.assert_buffer([], [])

        self.assertEqual(self.console.raw_input(), '')
        self.assert_buffer([], [])

        self.assertEqual(self.console.raw_input(), 'foobar')
        self.assert_buffer([], [None])

        with self.assertRaises(EOFError):
            self.console.raw_input()
        self.assert_buffer([], [None])
        with self.assertRaises(EOFError):
            self.console.raw_input()
        self.assert_buffer([], [None])

    def test_raw_input_one_chunk(self):
        data = b'hello\r\nworld\n\r\n\n\nfoobar'
        self.mock_sock.recv.side_effect = [data, b'']
        self.assert_buffer([], [])

        self.assertEqual(self.console.raw_input(), 'hello')
        self.assert_buffer([b'foobar'], ['world', '', '', ''])

        self.assertEqual(self.console.raw_input(), 'world')
        self.assert_buffer([b'foobar'], ['', '', ''])

        self.assertEqual(self.console.raw_input(), '')
        self.assert_buffer([b'foobar'], ['', ''])

        self.assertEqual(self.console.raw_input(), '')
        self.assert_buffer([b'foobar'], [''])

        self.assertEqual(self.console.raw_input(), '')
        self.assert_buffer([b'foobar'], [])

        self.assertEqual(self.console.raw_input(), 'foobar')
        self.assert_buffer([], [None])

        with self.assertRaises(EOFError):
            self.console.raw_input()
        self.assert_buffer([], [None])
        with self.assertRaises(EOFError):
            self.console.raw_input()
        self.assert_buffer([], [None])

    def test_raw_input_empty(self):
        self.mock_sock.recv.return_value = b''
        self.assert_buffer([], [])

        with self.assertRaises(EOFError):
            self.console.raw_input()
        self.assert_buffer([], [None])
        with self.assertRaises(EOFError):
            self.console.raw_input()
        self.assert_buffer([], [None])


if __name__ == '__main__':
    unittest.main()
