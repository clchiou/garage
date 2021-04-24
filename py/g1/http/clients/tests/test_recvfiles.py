import unittest
import unittest.mock

from pathlib import Path

from g1.http.clients import recvfiles


class RecvfilesTest(unittest.TestCase):

    def assert_chunk_decoder(
        self,
        decoder,
        expect_eof,
        expect_chunk_remaining,
    ):
        self.assertEqual(decoder.eof, expect_eof)
        self.assertEqual(decoder._chunk_remaining, expect_chunk_remaining)

    def test_decoder_chain(self):  # pylint: disable=no-self-use
        mock_file = unittest.mock.Mock(spec_set=['write', 'flush'])
        d0 = unittest.mock.Mock(spec_set=['decode', 'flush'])
        d1 = unittest.mock.Mock(spec_set=['decode', 'flush'])
        d2 = unittest.mock.Mock(spec_set=['decode', 'flush'])
        d0.decode.side_effect = lambda pieces: pieces + [b'd0-decode']
        d1.decode.side_effect = lambda pieces: pieces + [b'd1-decode']
        d2.decode.side_effect = lambda pieces: pieces + [b'd2-decode']
        d0.flush.return_value = [b'd0-flush']
        d1.flush.return_value = [b'd1-flush']
        d2.flush.return_value = [b'd2-flush']

        chain = recvfiles.DecoderChain(mock_file)
        chain.add(d0)
        chain.add(d1)
        chain.add(d2)
        chain.write(b'spam')
        chain.write(b'egg')
        chain.flush()

        mock_file.assert_has_calls([
            unittest.mock.call.write(b'spam'),
            unittest.mock.call.write(b'd0-decode'),
            unittest.mock.call.write(b'd1-decode'),
            unittest.mock.call.write(b'd2-decode'),
            unittest.mock.call.write(b'egg'),
            unittest.mock.call.write(b'd0-decode'),
            unittest.mock.call.write(b'd1-decode'),
            unittest.mock.call.write(b'd2-decode'),
            unittest.mock.call.write(b'd0-flush'),
            unittest.mock.call.write(b'd1-decode'),
            unittest.mock.call.write(b'd2-decode'),
            unittest.mock.call.write(b'd1-flush'),
            unittest.mock.call.write(b'd2-decode'),
            unittest.mock.call.write(b'd2-flush'),
        ])
        d0.assert_has_calls([
            unittest.mock.call.decode([b'spam']),
            unittest.mock.call.decode([b'egg']),
        ])
        d1.assert_has_calls([
            unittest.mock.call.decode([b'spam', b'd0-decode']),
            unittest.mock.call.decode([b'egg', b'd0-decode']),
            unittest.mock.call.decode([b'd0-flush']),
        ])
        d2.assert_has_calls([
            unittest.mock.call.decode([b'spam', b'd0-decode', b'd1-decode']),
            unittest.mock.call.decode([b'egg', b'd0-decode', b'd1-decode']),
            unittest.mock.call.decode([b'd0-flush', b'd1-decode']),
            unittest.mock.call.decode([b'd1-flush']),
        ])

    def test_chunk_decoder(self):
        d = recvfiles.ChunkDecoder()
        self.assert_chunk_decoder(d, False, -2)

        self.assertEqual(d.decode([]), [])
        self.assert_chunk_decoder(d, False, -2)

        output = []
        d._decode(b'4;foo bar\r\nab', output)
        self.assertEqual(output, [b'ab'])
        self.assert_chunk_decoder(d, False, 2)
        d._decode(b'cd', output)
        self.assertEqual(output, [b'ab', b'cd'])
        self.assert_chunk_decoder(d, False, 0)
        d._decode(b'\r', output)
        self.assertEqual(output, [b'ab', b'cd'])
        self.assert_chunk_decoder(d, False, -1)
        d._decode(b'\n', output)
        self.assertEqual(output, [b'ab', b'cd'])
        self.assert_chunk_decoder(d, False, -2)

        output = []
        d._decode(b'0;some parameters...\r\n', output)
        self.assertEqual(output, [])
        self.assert_chunk_decoder(d, True, 0)
        d._decode(b'\r\n', output)
        self.assertEqual(output, [])
        self.assert_chunk_decoder(d, True, -2)

        self.assertEqual(d.flush(), [])

    def test_chunk_decoder_more_data_at_the_end(self):
        d = recvfiles.ChunkDecoder()
        with self.assertRaisesRegex(
            AssertionError,
            r'expect empty collection, not b\'some more data\'',
        ):
            d.decode([b'0\r\n\r\nsome more data'])

        d = recvfiles.ChunkDecoder()
        with self.assertRaisesRegex(
            AssertionError,
            r'expect empty collection, not b\'some more data\'',
        ):
            d.decode([b'0\r\n\r\n', b'some more data'])

        d = recvfiles.ChunkDecoder()
        with self.assertRaisesRegex(
            AssertionError,
            r'expect false-value, not True',
        ):
            d.decode([b'0\r\n\r\n1\r\nx\r\n'])

    def test_chunk_decoder_one_byte_at_a_time(self):
        for content in [
            b'hello world',
            b'0123456789abcdeffedcba9876543210',
            Path(__file__).read_bytes(),
        ]:
            with self.subTest(content):
                # Two chunks, one byte at a time.
                output = []
                d = recvfiles.ChunkDecoder()
                self.assert_chunk_decoder(d, False, -2)
                for chunk_data in [
                    content[:len(content) // 2],
                    content[len(content) // 2:],
                    b'',
                ]:
                    chunk = b'%x\r\n%s\r\n' % (len(chunk_data), chunk_data)
                    for i in range(len(chunk)):
                        d._decode(memoryview(chunk[i:i + 1]), output)
                    self.assert_chunk_decoder(d, chunk_data == b'', -2)
                self.assertEqual(b''.join(output), content)

                # One byte per chunk.
                output = []
                d = recvfiles.ChunkDecoder()
                self.assert_chunk_decoder(d, False, -2)
                for i in range(len(content) + 1):
                    chunk_data = content[i:i + 1]
                    chunk = b'%x\r\n%s\r\n' % (len(chunk_data), chunk_data)
                    d._decode(memoryview(chunk), output)
                    self.assert_chunk_decoder(d, chunk_data == b'', -2)
                    self.assertEqual(b''.join(output), content[:i + 1])
                self.assertEqual(b''.join(output), content)


if __name__ == '__main__':
    unittest.main()
