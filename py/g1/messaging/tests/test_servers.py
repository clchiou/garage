import unittest

import uuid

from g1.asyncs import kernels
from g1.asyncs.bases import tasks

from g1.messaging import reqrep
from g1.messaging.reqrep import clients
from g1.messaging.reqrep import servers
from g1.messaging.wiredata import jsons


class InvalidRequestError(Exception):
    pass


class InternalServerError(Exception):
    pass


class TestInterface:

    @reqrep.raising(ValueError)
    def greet(self, name: str) -> str:
        raise NotImplementedError

    def f(self):
        raise NotImplementedError

    def g(self):
        raise NotImplementedError


# Don't inherit from ``TestInterface`` because we intentionally leave
# out ``f`` unimplemented.
class TestApplication:

    async def greet(self, name):
        return 'Hello, %s' % name

    async def g(self):
        return object()


Request, Response = reqrep.generate_interface_types(TestInterface, 'Test')

WIRE_DATA = jsons.JsonWireData()


class ServerTest(unittest.TestCase):

    def test_nested(self):
        server = servers.Server(
            TestApplication(), Request, Response, WIRE_DATA
        )
        with server:
            with self.assertRaisesRegex(AssertionError, r'expect None, not'):
                with server:
                    pass

    @kernels.with_kernel
    def test_serve(self):
        server = servers.Server(
            TestApplication(), Request, Response, WIRE_DATA
        )

        server.invalid_request_error = InvalidRequestError
        server.internal_server_error = InternalServerError

        wire_request = WIRE_DATA.to_lower(Request.greet(name='world'))
        self.assertEqual(
            WIRE_DATA.to_upper(
                Response,
                kernels.run(server._serve(wire_request)),
            ),
            Response(result='Hello, world'),
        )

        with self.assertLogs(servers.__name__, level='DEBUG') as cm:
            self.assertEqual(
                kernels.run(server._serve(b'')),
                server._invalid_request_error_wire,
            )
        self.assertRegex('\n'.join(cm.output), r'to_upper error: ')

        wire_request = WIRE_DATA.to_lower(Request.f())
        with self.assertLogs(servers.__name__, level='DEBUG') as cm:
            self.assertEqual(
                kernels.run(server._serve(wire_request)),
                server._invalid_request_error_wire,
            )
        self.assertRegex('\n'.join(cm.output), r'unknown method: f: ')

        wire_request = WIRE_DATA.to_lower(Request.g())
        with self.assertLogs(servers.__name__, level='DEBUG') as cm:
            self.assertEqual(
                kernels.run(server._serve(wire_request)),
                server._internal_server_error_wire,
            )
        self.assertRegex('\n'.join(cm.output), r'to_lower error: ')

    @kernels.with_kernel
    def test_end_to_end(self):
        app = TestApplication()
        with servers.Server(app, Request, Response, WIRE_DATA) as server:
            with clients.Client(Request, Response, WIRE_DATA) as client:
                url = 'inproc://%s' % uuid.uuid4()
                server.socket.listen(url)
                client.socket.dial(url)

                server_task = tasks.spawn(server.serve)

                client_task = tasks.spawn(client.m.greet(name='world'))

                with self.assertRaises(kernels.KernelTimeout):
                    kernels.run(timeout=0.005)

                self.assertTrue(client_task.is_completed())
                self.assertEqual(
                    client_task.get_result_nonblocking(), 'Hello, world'
                )

                self.assertFalse(server_task.is_completed())

                server.socket.close()
                kernels.run(timeout=1)

                self.assertTrue(server_task.is_completed())
                self.assertIsNone(server_task.get_result_nonblocking())


if __name__ == '__main__':
    unittest.main()
