import unittest
import unittest.mock

import ctypes

from g1.http.http2_servers import nghttp2 as ng
from g1.http.http2_servers import wsgi


class HttpSessionCallbacksTest(unittest.TestCase):

    @staticmethod
    def make_session():
        return wsgi.HttpSession(
            unittest.mock.Mock(),
            unittest.mock.Mock(),
            unittest.mock.Mock(),
            unittest.mock.Mock(),
        )

    @staticmethod
    def apply(func, self, *args):
        return func(None, *args, ctypes.pointer(ctypes.py_object(self)))

    def test_on_frame_recv(self):
        func = self.make_session().on_frame_recv

        self_mock = unittest.mock.Mock()
        frame = ng.nghttp2_frame()
        self.assertEqual(self.apply(func, self_mock, ctypes.pointer(frame)), 0)
        self_mock._stop_settings_timer.assert_not_called()
        self_mock._streams.get.assert_not_called()

        self_mock = unittest.mock.Mock()
        frame = ng.nghttp2_frame()
        frame.hd.type = ng.nghttp2_frame_type.NGHTTP2_SETTINGS
        frame.hd.flags |= ng.nghttp2_flag.NGHTTP2_FLAG_ACK
        self.assertEqual(self.apply(func, self_mock, ctypes.pointer(frame)), 0)
        self_mock._stop_settings_timer.assert_called_once()
        self_mock._streams.get.assert_not_called()

        self_mock = unittest.mock.Mock()
        frame = ng.nghttp2_frame()
        frame.hd.type = ng.nghttp2_frame_type.NGHTTP2_HEADERS
        frame.headers.cat = ng.nghttp2_headers_category.NGHTTP2_HCAT_REQUEST
        self.assertEqual(self.apply(func, self_mock, ctypes.pointer(frame)), 0)
        self_mock._stop_settings_timer.assert_not_called()
        self_mock._streams.get.assert_called_once()
        self_mock._streams.get.return_value.end_request.assert_not_called()

        self_mock = unittest.mock.Mock()
        frame = ng.nghttp2_frame()
        frame.hd.type = ng.nghttp2_frame_type.NGHTTP2_DATA
        frame.hd.flags |= ng.nghttp2_flag.NGHTTP2_FLAG_END_STREAM
        self.assertEqual(self.apply(func, self_mock, ctypes.pointer(frame)), 0)
        self_mock._stop_settings_timer.assert_not_called()
        self_mock._streams.get.assert_called_once()
        self_mock._streams.get.return_value.end_request.assert_called_once()

    def test_on_begin_headers(self):
        func = self.make_session().on_begin_headers

        self_mock = unittest.mock.MagicMock()
        frame = ng.nghttp2_frame()
        self.assertEqual(self.apply(func, self_mock, ctypes.pointer(frame)), 0)
        self_mock._streams.__setitem__.assert_not_called()

        self_mock = unittest.mock.MagicMock()
        frame = ng.nghttp2_frame()
        frame.hd.type = ng.nghttp2_frame_type.NGHTTP2_HEADERS
        frame.headers.cat = ng.nghttp2_headers_category.NGHTTP2_HCAT_REQUEST
        frame.hd.stream_id = 999
        self.assertEqual(self.apply(func, self_mock, ctypes.pointer(frame)), 0)
        self_mock._streams.__setitem__.assert_called_once_with(
            999, unittest.mock.ANY
        )

    def test_on_header(self):
        func = self.make_session().on_header

        self_mock = unittest.mock.Mock()
        frame = ng.nghttp2_frame()
        frame.hd.stream_id = 999
        self.assertEqual(
            self.apply(
                func,
                self_mock,
                ctypes.pointer(frame),
                b'header-name',
                11,
                b'header-value',
                12,
                0,
            ),
            0,
        )
        self_mock._streams.get.assert_called_once_with(999)
        self_mock._streams.get.return_value.set_header.assert_called_once_with(
            b'header-name', b'header-value'
        )

    def test_on_data_chunk_recv(self):
        func = self.make_session().on_data_chunk_recv

        self_mock = unittest.mock.Mock()
        data = ctypes.c_char_p(b'hello world')
        self.assertEqual(self.apply(func, self_mock, 0, 999, data, 11), 0)
        self_mock._streams.get.assert_called_once_with(999)
        (
            self_mock._streams.get.return_value \
            .write_request_body.assert_called_once_with(b'hello world')
        )

    def test_on_frame_send(self):
        func = self.make_session().on_frame_send

        self_mock = unittest.mock.Mock()
        frame = ng.nghttp2_frame()
        self.assertEqual(self.apply(func, self_mock, ctypes.pointer(frame)), 0)
        self_mock._start_settings_timer.assert_not_called()
        self_mock._rst_stream_if_not_closed.assert_not_called()

        self_mock = unittest.mock.Mock()
        frame = ng.nghttp2_frame()
        frame.hd.type = ng.nghttp2_frame_type.NGHTTP2_SETTINGS
        self.assertEqual(self.apply(func, self_mock, ctypes.pointer(frame)), 0)
        self_mock._start_settings_timer.assert_called_once()
        self_mock._rst_stream_if_not_closed.assert_not_called()

        self_mock = unittest.mock.Mock()
        self_mock._rst_stream_if_not_closed.return_value = 0
        frame = ng.nghttp2_frame()
        frame.hd.type = ng.nghttp2_frame_type.NGHTTP2_HEADERS
        frame.hd.flags |= ng.nghttp2_flag.NGHTTP2_FLAG_END_STREAM
        frame.hd.stream_id = 999
        self.assertEqual(self.apply(func, self_mock, ctypes.pointer(frame)), 0)
        self_mock._start_settings_timer.assert_not_called()
        self_mock._rst_stream_if_not_closed.assert_called_once_with(999)

    def test_on_frame_not_send(self):
        func = self.make_session().on_frame_not_send

        self_mock = unittest.mock.Mock()
        frame = ng.nghttp2_frame()
        self.assertEqual(
            self.apply(func, self_mock, ctypes.pointer(frame), 1), 0
        )

    def test_on_stream_close(self):
        func = self.make_session().on_stream_close

        self_mock = unittest.mock.Mock()
        self.assertEqual(self.apply(func, self_mock, 999, 0), 0)
        self_mock._streams.pop.assert_called_once_with(999, None)
        self_mock._streams.pop.return_value.close.assert_called_once()

    def test_data_source_read(self):
        func = self.make_session().data_source_read

        self_mock = unittest.mock.MagicMock()
        stream = self_mock._streams.__getitem__.return_value
        stream.read_response_body.return_value = b'hello world'
        buf = ctypes.create_string_buffer(11)
        data_flags = ctypes.c_uint32()
        self.assertEqual(
            self.apply(
                func,
                self_mock,
                999,
                buf,
                11,
                ctypes.pointer(data_flags),
                ctypes.pointer(ng.nghttp2_data_source()),
            ), 11
        )
        self_mock._streams.__getitem__.assert_called_once_with(999)
        stream.read_response_body.assert_called_once_with(11)
        self.assertEqual(data_flags.value, 0)
        self.assertEqual(buf.raw, b'hello world')

        self_mock = unittest.mock.MagicMock()
        stream = self_mock._streams.__getitem__.return_value
        stream.read_response_body.return_value = b''
        buf = ctypes.create_string_buffer(11)
        data_flags = ctypes.c_uint32()
        self.assertEqual(
            self.apply(
                func,
                self_mock,
                999,
                buf,
                11,
                ctypes.pointer(data_flags),
                ctypes.pointer(ng.nghttp2_data_source()),
            ), 0
        )
        self_mock._streams.__getitem__.assert_called_once_with(999)
        stream.read_response_body.assert_called_once_with(11)
        self.assertEqual(
            data_flags.value, ng.nghttp2_data_flag.NGHTTP2_DATA_FLAG_EOF
        )
        self_mock._rst_stream_if_not_closed.assert_called_once_with(999)
        self.assertEqual(buf.raw, b'\x00' * 11)

        self_mock = unittest.mock.MagicMock()
        stream = self_mock._streams.__getitem__.return_value
        stream.read_response_body.return_value = None
        buf = ctypes.create_string_buffer(11)
        data_flags = ctypes.c_uint32()
        self.assertEqual(
            self.apply(
                func,
                self_mock,
                999,
                buf,
                11,
                ctypes.pointer(data_flags),
                ctypes.pointer(ng.nghttp2_data_source()),
            ),
            ng.nghttp2_error.NGHTTP2_ERR_DEFERRED,
        )
        self_mock._streams.__getitem__.assert_called_once_with(999)
        stream.read_response_body.assert_called_once_with(11)
        self.assertEqual(data_flags.value, 0)
        self.assertEqual(buf.raw, b'\x00' * 11)


if __name__ == '__main__':
    unittest.main()
