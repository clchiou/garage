import unittest

from g1.asyncs import kernels
from g1.messaging import reqrep
from g1.messaging.reqrep import inprocs


class InternalServerError(Exception):
    pass


@reqrep.raising(InternalServerError)
class TestInterface:

    @reqrep.raising(ZeroDivisionError)
    async def div(self, x: float, y: float) -> float:
        del self  # Unused.
        return x / y

    async def boom(self) -> str:
        del self  # Unused.
        raise ValueError


Request, Response = reqrep.generate_interface_types(TestInterface, 'Test')


class InprocServerTest(unittest.TestCase):

    def setUp(self):
        super().setUp()
        self.server = inprocs.InprocServer(
            TestInterface(),
            Request,
            Response,
            internal_server_error_type=InternalServerError,
        )

    @kernels.with_kernel
    def test_zero_division_error(self):
        self.assertEqual(kernels.run(self.server.m.div(x=4, y=2)), 2)
        with self.assertRaises(ZeroDivisionError):
            kernels.run(self.server.m.div(x=1, y=0))

    @kernels.with_kernel
    def test_internal_server_error(self):
        with self.assertRaises(InternalServerError):
            kernels.run(self.server.m.boom())


if __name__ == '__main__':
    unittest.main()
