import unittest

import uuid

import nng

from g1.asyncs import kernels
from g1.asyncs.bases import tasks

from g1.messaging import reqrep
from g1.messaging.reqrep import clients
from g1.messaging.wiredata import jsons


class TestInterface:

    @staticmethod
    def some_static_method():
        pass

    @classmethod
    def some_class_method(cls):
        pass

    @property
    def some_property(self):
        pass

    def _private_method(self):
        pass

    @reqrep.raising(ValueError)
    def greet(self, name: str) -> str:
        raise NotImplementedError

    def f(self):
        raise NotImplementedError


Request, Response = reqrep.generate_interface_types(TestInterface, 'Test')

WIRE_DATA = jsons.JsonWireData()


class ClientTest(unittest.TestCase):

    def test_method_names(self):
        with clients.Client(Request, Response, WIRE_DATA) as client:
            self.assertEqual(sorted(client.m), ['f', 'greet'])

    @kernels.with_kernel
    def test_success(self):
        with clients.Client(Request, Response, WIRE_DATA) as client:
            with nng.Socket(nng.Protocols.REP0) as socket:
                url = 'inproc://%s' % uuid.uuid4()
                socket.listen(url)
                client.socket.dial(url)

                task = tasks.spawn(client.m.greet(name='world'))
                with self.assertRaises(kernels.KernelTimeout):
                    kernels.run(timeout=0)

                request = WIRE_DATA.to_upper(Request, socket.recv())
                self.assertEqual(request.args, Request.m.greet(name='world'))

                response = Response(
                    result=Response.Result(greet='hello world')
                )
                socket.send(WIRE_DATA.to_lower(response))

                kernels.run(timeout=1)
                self.assertTrue(task.is_completed())
                self.assertEqual(task.get_result_nonblocking(), 'hello world')

    @kernels.with_kernel
    def test_error(self):
        with clients.Client(Request, Response, WIRE_DATA) as client:
            with nng.Socket(nng.Protocols.REP0) as socket:
                url = 'inproc://%s' % uuid.uuid4()
                socket.listen(url)
                client.socket.dial(url)

                task = tasks.spawn(client.m.greet(name='world'))
                with self.assertRaises(kernels.KernelTimeout):
                    kernels.run(timeout=0)

                request = WIRE_DATA.to_upper(Request, socket.recv())
                self.assertEqual(request.args, Request.m.greet(name='world'))

                response = Response(
                    error=Response.Error(value_error=ValueError('oops'))
                )
                socket.send(WIRE_DATA.to_lower(response))

                kernels.run(timeout=1)
                self.assertTrue(task.is_completed())
                with self.assertRaisesRegex(ValueError, r'oops'):
                    task.get_result_nonblocking()

    @kernels.with_kernel
    def test_invalid_response(self):
        with clients.Client(Request, Response, WIRE_DATA) as client:
            with nng.Socket(nng.Protocols.REP0) as socket:
                url = 'inproc://%s' % uuid.uuid4()
                socket.listen(url)
                client.socket.dial(url)

                task = tasks.spawn(client.m.greet(name='world'))
                with self.assertRaises(kernels.KernelTimeout):
                    kernels.run(timeout=0)

                socket.recv()
                socket.send(b'{"result": {"greet": 42}, "error": null}')

                kernels.run(timeout=1)
                self.assertTrue(task.is_completed())
                with self.assertRaisesRegex(AssertionError, r'expect.*str'):
                    task.get_result_nonblocking()


if __name__ == '__main__':
    unittest.main()
