import unittest

from garage.multiprocessing import RpcConnectionError
from garage.multiprocessing import RpcError
from garage.multiprocessing import python


DEF_FUNC_1 = '''
def func_1(a, b, c):
    return a + b + c
'''


DEF_FUNC_2 = '''
def func_2(a, b, c):
    raise RuntimeError
'''


class TestPython(unittest.TestCase):

    def test_python(self):
        with python() as connector:
            with connector.connect() as stub:
                stub.server_vars.graceful_shutdown = True

            with connector.connect() as stub:
                stub.vars.x = 1
                stub.execute('y = x * 2')
                stub.execute(DEF_FUNC_1)
                stub.execute(DEF_FUNC_2)
            with connector.connect() as stub:
                self.assertEqual(1, stub.vars.x)
                self.assertEqual(2, stub.vars.y)
                self.assertEqual(6, stub.funcs.func_1(1, b=2, c=3))
                with self.assertRaises(RpcError):
                    stub.funcs.func_1()
                with self.assertRaises(RpcError):
                    stub.funcs.func_2(1, b=2, c=3)

            with connector.connect() as stub:
                del stub.vars.x
            with connector.connect() as stub:
                with self.assertRaises(AttributeError):
                    stub.vars.x
                with self.assertRaises(AttributeError):
                    del stub.vars.z

    def test_repeated_shutdown(self):
        with python() as connector:
            with connector.connect() as stub:
                for _ in range(3):
                    stub.shutdown()
            for _ in range(3):
                connector.shutdown()

            with self.assertRaises(RpcConnectionError):
                with connector.connect():
                    pass

    def test_repeated_close(self):
        with python() as connector:
            for _ in range(3):
                with connector.connect() as stub:
                    for _ in range(3):
                        stub.close()


if __name__ == '__main__':
    unittest.main()
