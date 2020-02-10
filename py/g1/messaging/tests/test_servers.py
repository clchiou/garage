import unittest
import unittest.mock

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


@reqrep.raising(InvalidRequestError, InternalServerError)
class TestInterface:

    @reqrep.raising(ValueError)
    def greet(self, name: str) -> str:
        raise NotImplementedError

    def f(self):
        raise NotImplementedError

    def g(self):
        raise NotImplementedError

    def h(self):
        raise NotImplementedError


@reqrep.raising(InternalServerError)
class TestOnlyOneError:

    def f(self):
        raise NotImplementedError


# Don't inherit from ``TestInterface`` because we intentionally leave
# out ``f`` unimplemented.
class TestApplication:

    async def greet(self, name):
        return 'Hello, %s' % name

    async def g(self):
        return object()

    async def h(self):
        # Test error that is not declared in the interface.
        raise RuntimeError


Request, Response = reqrep.generate_interface_types(TestInterface, 'Test')

WIRE_DATA = jsons.JsonWireData()


class ServerTest(unittest.TestCase):

    def test_only_one_error(self):
        request_type, response_type = \
            reqrep.generate_interface_types(TestOnlyOneError)
        server = servers.Server(
            TestOnlyOneError(),
            request_type,
            response_type,
            WIRE_DATA,
        )
        self.assertEqual(
            server._declared_error_types,
            {InternalServerError: 'internal_server_error'},
        )

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
            TestApplication(),
            Request,
            Response,
            WIRE_DATA,
            invalid_request_error=InvalidRequestError(),
            internal_server_error=InternalServerError(),
        )

        wire_request = WIRE_DATA.to_lower(
            Request(args=Request.m.greet(name='world'))
        )
        self.assertEqual(
            WIRE_DATA.to_upper(
                Response,
                kernels.run(server._serve(wire_request)),
            ),
            Response(result=Response.Result(greet='Hello, world')),
        )

        with self.assertLogs(servers.__name__, level='DEBUG') as cm:
            self.assertEqual(
                kernels.run(server._serve(b'')),
                server._invalid_request_error_wire,
            )
        self.assertRegex('\n'.join(cm.output), r'to_upper error: ')

        wire_request = WIRE_DATA.to_lower(Request(args=Request.m.f()))
        with self.assertLogs(servers.__name__, level='DEBUG') as cm:
            self.assertEqual(
                kernels.run(server._serve(wire_request)),
                server._invalid_request_error_wire,
            )
        self.assertRegex('\n'.join(cm.output), r'unknown method: f: ')

        wire_request = WIRE_DATA.to_lower(Request(args=Request.m.g()))
        with self.assertLogs(servers.__name__, level='DEBUG') as cm:
            self.assertEqual(
                kernels.run(server._serve(wire_request)),
                server._internal_server_error_wire,
            )
        self.assertRegex('\n'.join(cm.output), r'to_lower error: ')

        wire_request = WIRE_DATA.to_lower(Request(args=Request.m.h()))
        with self.assertLogs(servers.__name__, level='DEBUG') as cm:
            self.assertEqual(
                kernels.run(server._serve(wire_request)),
                server._internal_server_error_wire,
            )
        self.assertRegex('\n'.join(cm.output), r'server error: ')

    @kernels.with_kernel
    def test_end_to_end(self):

        def do_test(client, server, server_serve):
            url = 'inproc://%s' % uuid.uuid4()
            server.socket.listen(url)
            client.socket.dial(url)

            server_task = tasks.spawn(server_serve)

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

        app = TestApplication()
        with servers.Server(app, Request, Response, WIRE_DATA) as server:
            with clients.Client(Request, Response, WIRE_DATA) as client:
                do_test(client, server, server.serve)

        app = TestApplication()
        server = servers.Server(app, Request, Response, WIRE_DATA)
        with clients.Client(Request, Response, WIRE_DATA) as client:
            do_test(client, server, servers.run_server(server))

    @kernels.with_kernel
    def test_run_server(self):

        called = [0]

        async def noop():
            called[0] += 1

        async def err():
            raise ValueError

        server_mock = unittest.mock.MagicMock()
        server_mock.serve = noop

        self.assertIsNone(
            kernels.run(
                servers.run_server(server_mock, parallelism=4),
                timeout=1,
            )
        )
        self.assertEqual(called[0], 4)

        server_mock.serve = err
        with self.assertRaises(ValueError):
            kernels.run(
                servers.run_server(server_mock, parallelism=4),
                timeout=1,
            )


if __name__ == '__main__':
    unittest.main()
