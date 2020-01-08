import unittest
import unittest.mock

import subprocess
from pathlib import Path

from g1.scripts import bases


class BasesTest(unittest.TestCase):

    def tearDown(self):
        bases._CONTEXT.clear()
        super().tearDown()

    def test_doing_capture_output(self):
        self.do_test_using(
            bases.doing_capture_output, bases._CAPTURE_OUTPUT, True, False
        )

    def test_doing_check(self):
        self.do_test_using(bases.doing_check, bases._CHECK, True, False)

    def test_get_dry_run(self):
        self.assertEqual(bases.get_dry_run(), False)
        with bases.doing_dry_run():
            self.assertEqual(bases.get_dry_run(), True)

    def test_doing_dry_run(self):
        self.do_test_using(bases.doing_dry_run, bases._DRY_RUN, True, False)

    def test_using_cwd(self):
        self.do_test_using(bases.using_cwd, bases._CWD, 'p', 'q')
        self.do_test_using(bases.using_cwd, bases._CWD, 'p', None)

    def test_using_input(self):
        self.do_test_using(bases.using_input, bases._INPUT, b'1', b'2')
        self.do_test_using(bases.using_input, bases._INPUT, b'1', None)

    def test_using_stdout(self):
        self.do_test_using(
            bases.using_stdout, bases._STDOUT, None, subprocess.PIPE
        )

    def test_using_stderr(self):
        self.do_test_using(
            bases.using_stderr, bases._STDERR, None, subprocess.DEVNULL
        )

    def test_using_sudo(self):
        self.do_test_using(bases.using_sudo, bases._SUDO, True, False)

    def test_preserving_sudo_envs(self):
        self.do_test_using(
            bases.preserving_sudo_envs, bases._SUDO_ENVS, [], ['X']
        )

    def do_test_using(self, using, name, value1, value2):
        self.assertEqual(bases._CONTEXT, {})
        with using(value1):
            self.assertEqual(bases._CONTEXT, {name: value1})
            with using(value2):
                self.assertEqual(bases._CONTEXT, {name: value2})
            self.assertEqual(bases._CONTEXT, {name: value1})
        self.assertEqual(bases._CONTEXT, {})

    def test_using_relative_cwd(self):
        cwd = Path.cwd()
        self.assertEqual(bases._CONTEXT, {})
        self.assertEqual(bases.get_cwd(), cwd)
        with bases.using_relative_cwd(None):
            self.assertEqual(bases._CONTEXT, {bases._CWD: None})
            self.assertEqual(bases.get_cwd(), cwd)
            with bases.using_relative_cwd('p'):
                self.assertEqual(bases._CONTEXT, {bases._CWD: cwd / 'p'})
                self.assertEqual(bases.get_cwd(), cwd / 'p')
            with bases.using_relative_cwd('../q'):
                self.assertEqual(bases._CONTEXT, {bases._CWD: cwd / '../q'})
                self.assertEqual(bases.get_cwd(), cwd / '../q')
        self.assertEqual(bases._CONTEXT, {})
        self.assertEqual(bases.get_cwd(), cwd)
        with bases.using_relative_cwd('../q'):
            self.assertEqual(bases._CONTEXT, {bases._CWD: cwd / '../q'})
            self.assertEqual(bases.get_cwd(), cwd / '../q')
        with bases.using_relative_cwd('/r'):
            self.assertEqual(bases._CONTEXT, {bases._CWD: Path('/r')})
            self.assertEqual(bases.get_cwd(), Path('/r'))
        self.assertEqual(bases._CONTEXT, {})
        self.assertEqual(bases.get_cwd(), cwd)

    @staticmethod
    @unittest.mock.patch(bases.__name__ + '.subprocess')
    def test_popen(subprocess_mock):
        bases.popen(['cat', Path('foo')])
        subprocess_mock.Popen.assert_called_once_with(['cat', 'foo'], cwd=None)

    @staticmethod
    @unittest.mock.patch(bases.__name__ + '.subprocess')
    def test_run(subprocess_mock):
        bases.run(['cat', Path('foo')])
        subprocess_mock.run.assert_called_once_with(
            ['cat', 'foo'],
            capture_output=False,
            check=True,
            cwd=None,
            input=None,
        )

    @staticmethod
    @unittest.mock.patch(bases.__name__ + '.subprocess')
    def test_run_with_non_defaults(subprocess_mock):
        with bases.doing_check(False):
            with bases.using_sudo(), bases.preserving_sudo_envs(['X', 'Y']):
                with bases.using_cwd(Path('foo')):
                    bases.run(['echo'])
        subprocess_mock.run.assert_called_once_with(
            ['sudo', '--non-interactive', '--preserve-env=X,Y', 'echo'],
            capture_output=False,
            check=False,
            cwd=Path('foo'),
            input=None,
        )

    @staticmethod
    @unittest.mock.patch(bases.__name__ + '.subprocess')
    def test_run_with_dry_run(subprocess_mock):
        with bases.doing_dry_run():
            bases.run(['echo'])
        subprocess_mock.run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
