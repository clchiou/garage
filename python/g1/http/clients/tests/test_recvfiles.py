import unittest
import unittest.mock

from pathlib import Path

from g1.http.clients import recvfiles

States = recvfiles.ChunkDecoder._States


class RecvfilesTest(unittest.TestCase):

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

    def assert_chunk_decoder(
        self,
        decoder,
        expect_state,
        expect_buffer,
        expect_chunk_remaining,
    ):
        self.assertIs(decoder._state, expect_state)
        self.assertEqual(decoder._buffer_size, len(expect_buffer))
        self.assertEqual(
            bytes(decoder._buffer[:decoder._buffer_size]),
            expect_buffer,
        )
        self.assertEqual(decoder._chunk_remaining, expect_chunk_remaining)

    def test_chunk_decoder(self):
        d = recvfiles.ChunkDecoder()
        self.assert_chunk_decoder(d, States.CHUNK_SIZE, b'', 0)

        self.assertEqual(d.decode([]), [])
        self.assert_chunk_decoder(d, States.CHUNK_SIZE, b'', 0)

        self.assertEqual(
            d.decode([b'', b'b\r\nhello ', b'world', b'\r\n0\r\n\r\n']),
            [b'hello ', b'world'],
        )
        self.assert_chunk_decoder(d, States.END, b'', 0)

        self.assertEqual(d.flush(), [])
        self.assert_chunk_decoder(d, States.END, b'', 0)

        d = recvfiles.ChunkDecoder()
        self.assert_chunk_decoder(d, States.CHUNK_SIZE, b'', 0)

        self.assertEqual(d.decode([b'4;foo bar\r\nab']), [b'ab'])
        self.assert_chunk_decoder(d, States.CHUNK_DATA, b'', 2)
        self.assertEqual(d.decode([b'cd']), [b'cd'])
        self.assert_chunk_decoder(d, States.CHUNK_DATA_CR, b'', 0)
        self.assertEqual(d.decode([b'\r']), [])
        self.assert_chunk_decoder(d, States.CHUNK_DATA_LF, b'', 0)
        self.assertEqual(d.decode([b'\n']), [])
        self.assert_chunk_decoder(d, States.CHUNK_SIZE, b'', 0)

        self.assertEqual(d.decode([b'0;some parameters...\r\n']), [])
        self.assert_chunk_decoder(d, States.TRAILER_SECTION, b'', 0)

        self.assertEqual(d.decode([b'trailer ']), [])
        self.assert_chunk_decoder(d, States.TRAILER_SECTION, b'', 8)
        self.assertEqual(d.decode([b'data']), [])
        self.assert_chunk_decoder(d, States.TRAILER_SECTION, b'', 12)
        self.assertEqual(d.decode([b'\r']), [])
        self.assert_chunk_decoder(d, States.TRAILER_SECTION_LF, b'', 12)
        self.assertEqual(d.decode([b'\n']), [])
        self.assert_chunk_decoder(d, States.TRAILER_SECTION, b'', 0)
        self.assertEqual(d.decode([b'\r']), [])
        self.assert_chunk_decoder(d, States.TRAILER_SECTION_LF, b'', 0)
        self.assertEqual(d.decode([b'\n']), [])
        self.assert_chunk_decoder(d, States.END, b'', 0)

        self.assertEqual(d.flush(), [])
        self.assert_chunk_decoder(d, States.END, b'', 0)

    def test_chunk_decoder_header(self):
        d = recvfiles.ChunkDecoder()
        self.assert_chunk_decoder(d, States.CHUNK_SIZE, b'', 0)
        self.assertEqual(d.decode([b'1']), [])
        self.assert_chunk_decoder(d, States.CHUNK_SIZE, b'1', 0)
        self.assertEqual(d.decode([b'0']), [])
        self.assert_chunk_decoder(d, States.CHUNK_SIZE, b'10', 0)
        self.assertEqual(d.decode([b';abc']), [])
        self.assert_chunk_decoder(d, States.CHUNK_EXTENSION, b'10', 0)
        self.assertEqual(d.decode([b';def']), [])
        self.assert_chunk_decoder(d, States.CHUNK_EXTENSION, b'10', 0)
        self.assertEqual(d.decode([b';ghi\r']), [])
        self.assert_chunk_decoder(d, States.CHUNK_HEADER_LF, b'10', 0)
        self.assertEqual(d.decode([b'\n']), [])
        self.assert_chunk_decoder(d, States.CHUNK_DATA, b'', 0x10)

        d = recvfiles.ChunkDecoder()
        self.assert_chunk_decoder(d, States.CHUNK_SIZE, b'', 0)
        self.assertEqual(d.decode([b'123\r']), [])
        self.assert_chunk_decoder(d, States.CHUNK_HEADER_LF, b'123', 0)
        self.assertEqual(d.decode([b'\n']), [])
        self.assert_chunk_decoder(d, States.CHUNK_DATA, b'', 0x123)

        d = recvfiles.ChunkDecoder()
        self.assert_chunk_decoder(d, States.CHUNK_SIZE, b'', 0)
        self.assertEqual(d.decode([b'000']), [])
        self.assert_chunk_decoder(d, States.CHUNK_SIZE, b'000', 0)
        self.assertEqual(d.decode([b'\r\n']), [])
        self.assert_chunk_decoder(d, States.TRAILER_SECTION, b'', 0)

    def test_chunk_decoder_data(self):
        d = recvfiles.ChunkDecoder()
        self.assertEqual(d.decode([b'b\r\n']), [])
        self.assert_chunk_decoder(d, States.CHUNK_DATA, b'', 11)
        self.assertEqual(d.decode([b'\r\n'] * 5), [b'\r\n'] * 5)
        self.assert_chunk_decoder(d, States.CHUNK_DATA, b'', 1)
        self.assertEqual(d.decode([b'x']), [b'x'])
        self.assert_chunk_decoder(d, States.CHUNK_DATA_CR, b'', 0)
        self.assertEqual(d.decode([b'\r']), [])
        self.assert_chunk_decoder(d, States.CHUNK_DATA_LF, b'', 0)
        self.assertEqual(d.decode([b'\n']), [])
        self.assert_chunk_decoder(d, States.CHUNK_SIZE, b'', 0)

        d = recvfiles.ChunkDecoder()
        self.assertEqual(d.decode([b'2\r\n']), [])
        self.assert_chunk_decoder(d, States.CHUNK_DATA, b'', 2)
        self.assertEqual(d.decode([b'ab\r\n3']), [b'ab'])
        self.assert_chunk_decoder(d, States.CHUNK_SIZE, b'3', 0)

    def test_chunk_decoder_trailer_section(self):
        d = recvfiles.ChunkDecoder()
        self.assertEqual(d.decode([b'0\r\n']), [])
        self.assert_chunk_decoder(d, States.TRAILER_SECTION, b'', 0)
        self.assertEqual(d.decode([b'abc ']), [])
        self.assert_chunk_decoder(d, States.TRAILER_SECTION, b'', 4)
        self.assertEqual(d.decode([b'xyz']), [])
        self.assert_chunk_decoder(d, States.TRAILER_SECTION, b'', 7)
        self.assertEqual(d.decode([b'\r']), [])
        self.assert_chunk_decoder(d, States.TRAILER_SECTION_LF, b'', 7)
        self.assertEqual(d.decode([b'\n']), [])
        self.assert_chunk_decoder(d, States.TRAILER_SECTION, b'', 0)
        self.assertEqual(d.decode([b'\r']), [])
        self.assert_chunk_decoder(d, States.TRAILER_SECTION_LF, b'', 0)
        self.assertEqual(d.decode([b'\n']), [])
        self.assert_chunk_decoder(d, States.END, b'', 0)

    def test_chunk_decoder_incomplete_last_chunk(self):
        d = recvfiles.ChunkDecoder()
        self.assertEqual(d.decode([b'0\r\n']), [])
        self.assert_chunk_decoder(d, States.TRAILER_SECTION, b'', 0)
        self.assertEqual(d.flush(), [])

        # This is also incomplete, but for now we err out in this case.
        d = recvfiles.ChunkDecoder()
        self.assertEqual(d.decode([b'0\r\n\r']), [])
        self.assert_chunk_decoder(d, States.TRAILER_SECTION_LF, b'', 0)
        with self.assertRaisesRegex(
            AssertionError,
            r'expect .*TRAILER_SECTION_LF:.* in .*TRAILER_SECTION:.*END:',
        ):
            d.flush()

    def test_chunk_decoder_ignore_data_after_the_end(self):
        d = recvfiles.ChunkDecoder()
        self.assertEqual(d.decode([b'0\r\n\r\nsome more data']), [])
        self.assert_chunk_decoder(d, States.END, b'', 0)

    def test_chunk_decoder_one_byte_at_a_time(self):
        for content in [
            b'hello world',
            b'0123456789abcdeffedcba9876543210',
            Path(__file__).read_bytes(),
        ]:
            with self.subTest(content):
                # Two chunks, one byte at a time.
                d = recvfiles.ChunkDecoder()
                output = []
                for chunk_data in [
                    content[:len(content) // 2],
                    content[len(content) // 2:],
                    b'',
                ]:
                    chunk = memoryview(
                        b'%x\r\n%s\r\n' % (len(chunk_data), chunk_data)
                    )
                    for i in range(len(chunk)):
                        d._decode(chunk[i:i + 1], output)
                self.assert_chunk_decoder(d, States.END, b'', 0)
                self.assertEqual(b''.join(output), content)

                # One byte per chunk.
                d = recvfiles.ChunkDecoder()
                output = []
                for i in range(len(content) + 1):
                    chunk_data = content[i:i + 1]
                    chunk = memoryview(
                        b'%x\r\n%s\r\n' % (len(chunk_data), content[i:i + 1])
                    )
                    d._decode(chunk, output)
                self.assert_chunk_decoder(d, States.END, b'', 0)
                self.assertEqual(b''.join(output), content)


if __name__ == '__main__':
    unittest.main()
