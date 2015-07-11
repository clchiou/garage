import unittest

from garage.multiprocessing import RpcConnectionError
from garage.multiprocessing import python


class TestPython(unittest.TestCase):

    def test_python(self):
        with python() as connector:
            with connector.connect() as stub:
                stub.server_vars.graceful_shutdown = True

            with connector.connect() as stub:
                stub.vars.x = 1
                stub.execute('y = x * 2')
            with connector.connect() as stub:
                self.assertEqual(1, stub.vars.x)
                self.assertEqual(2, stub.vars.y)

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
