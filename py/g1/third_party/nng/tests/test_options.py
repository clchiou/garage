import unittest

import uuid

import nng


class OptionsTest(unittest.TestCase):

    @staticmethod
    def iter_properties(obj):
        cls = type(obj)
        for name in dir(cls):
            field = getattr(cls, name)
            if isinstance(field, property):
                yield name, field

    def assert_prop(self, obj, name, prop=None):
        if prop is None:
            prop = getattr(type(obj), name)
        # For now, don't test unreadable options.
        if not prop.fget:
            return
        value = getattr(obj, name)
        if prop.fset:
            setattr(obj, name, value)
            self.assertEqual(getattr(obj, name), value)

    def assert_no_prop(self, obj, name, prop=None):
        if prop is None:
            prop = getattr(type(obj), name)
        # For now, don't test unreadable options.
        if not prop.fget:
            return
        with self.assertRaises(nng.Errors.ENOTSUP):
            getattr(obj, name)

    def test_socket_options(self):

        protocol_options = {
            'polyamorous': nng.Protocols.PAIR1,
            'resend_time': nng.Protocols.REQ0,
            'survey_time': nng.Protocols.SURVEYOR0,
        }

        with nng.Socket(nng.Protocols.REP0) as socket:
            for name, prop in self.iter_properties(socket):
                with self.subTest(name):
                    if name in protocol_options:
                        self.assert_no_prop(socket, name, prop)
                    else:
                        self.assert_prop(socket, name, prop)

        for name, protocol in protocol_options.items():
            with self.subTest((name, protocol)):
                with nng.Socket(protocol) as socket:
                    self.assert_prop(socket, name)

        with nng.Socket(nng.Protocols.SUB0) as socket:
            socket.subscribe('topic-1')
            socket.unsubscribe('topic-1')
            with self.assertRaises(nng.Errors.ENOENT):
                socket.unsubscribe('topic-2')

    def test_context_options(self):

        protocol_options = {
            'resend_time': nng.Protocols.REQ0,
            'survey_time': nng.Protocols.SURVEYOR0,
        }

        with nng.Socket(nng.Protocols.REP0) as socket:
            with nng.Context(socket) as context:
                for name, prop in self.iter_properties(context):
                    with self.subTest(name):
                        if name in protocol_options:
                            self.assert_no_prop(context, name, prop)
                        else:
                            self.assert_prop(context, name, prop)

        for name, protocol in protocol_options.items():
            with self.subTest((name, protocol)):
                with nng.Socket(protocol) as socket:
                    with nng.Context(socket) as context:
                        self.assert_prop(context, name)

        with nng.Socket(nng.Protocols.SUB0) as socket:
            with nng.Context(socket) as context:
                context.subscribe('topic-1')
                context.unsubscribe('topic-1')
                with self.assertRaises(nng.Errors.ENOENT):
                    context.unsubscribe('topic-2')

    def test_inproc_options(self):
        with nng.Socket(nng.Protocols.REP0) as socket:
            for endpoint in (
                socket.dial('inproc://%s' % uuid.uuid4(), create_only=True),
                socket.listen('inproc://%s' % uuid.uuid4(), create_only=True),
            ):
                for name, prop in self.iter_properties(endpoint):
                    with self.subTest((endpoint, name)):
                        if (
                            name.startswith('ipc_') or name.startswith('tls_')
                            or name.startswith('ws_')
                            or name == 'tcp_bound_port'
                        ):
                            self.assert_no_prop(endpoint, name, prop)
                        else:
                            self.assert_prop(endpoint, name, prop)

    def test_tcp_options(self):
        with nng.Socket(nng.Protocols.REP0) as socket:

            # Set ``create_only`` to false to have ``tcp_bound_port``.
            endpoint = socket.listen('tcp://127.0.0.1:0')
            for name, prop in self.iter_properties(endpoint):
                with self.subTest((endpoint, name)):
                    if (
                        name.startswith('ipc_') or name.startswith('tls_')
                        or name.startswith('ws_') or name == 'remote_address'
                    ):
                        self.assert_no_prop(endpoint, name, prop)
                    else:
                        self.assert_prop(endpoint, name, prop)

            endpoint = socket.dial('tcp://127.0.0.1:8000', create_only=True)
            for name, prop in self.iter_properties(endpoint):
                with self.subTest((endpoint, name)):
                    if (
                        name.startswith('ipc_') or name.startswith('tls_')
                        or name.startswith('ws_') or name == 'remote_address'
                        or name == 'tcp_bound_port'
                    ):
                        self.assert_no_prop(endpoint, name, prop)
                    else:
                        self.assert_prop(endpoint, name, prop)


if __name__ == '__main__':
    unittest.main()
