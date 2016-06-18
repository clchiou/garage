import unittest

from subprocess import call, check_call, check_output


class AppsTest(unittest.TestCase):

    # NOTE: Use test name format "test_XXXX_..." to ensure test order.
    # (We need this because integration tests are stateful.)

    def test_0000_no_pods(self):
        self.assertEqual([], list_pods())


def list_pods():
    output = check_output(['python3', '-m', 'ops.apps', '-v', 'list-pods'])
    output = output.decode('ascii').split('\n')
    return list(filter(None, map(str.strip, output)))


if __name__ == '__main__':
    unittest.main()
