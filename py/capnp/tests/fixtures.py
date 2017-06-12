__all__ = [
    'Fixture',
]

from pathlib import Path
import contextlib
import subprocess
import tempfile
import unittest


class Fixture(unittest.TestCase):

    TESTDATA_PATH = Path(__file__).parent / 'testdata'

    @classmethod
    def compile(cls, path):
        """Compile schema file in testdata/ directory."""
        return subprocess.check_output([
            'capnp', 'compile', '-o-', str(cls.TESTDATA_PATH  / path),
        ])

    @staticmethod
    @contextlib.contextmanager
    def using_temp_file(content):
        with tempfile.NamedTemporaryFile() as file:
            Path(file.name).write_bytes(content)
            yield file.name

    @classmethod
    def decode(cls, schema_path, schema, message_bytes, *, packed=False):
        # This is useful for debugging, but don't compare the result to
        # str(struct) literally since they are rarely string-identical.
        cmd = ['capnp', 'decode']
        if packed:
            cmd.append('--packed')
        cmd.extend([str(cls.TESTDATA_PATH  / schema_path), schema.name])
        return subprocess.check_output(cmd, input=message_bytes).decode('utf8')

    @classmethod
    def encode(cls, schema_path, schema, struct, *, packed=False):
        cmd = ['capnp', 'encode']
        if packed:
            cmd.append('--packed')
        cmd.extend([str(cls.TESTDATA_PATH  / schema_path), schema.name])
        return subprocess.check_output(cmd, input=str(struct).encode('utf8'))
