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
    def encode(cls, schema_path, schema, struct, *, packed=False):
        cmd = ['capnp', 'encode']
        if packed:
            cmd.append('--packed')
        cmd.extend([str(cls.TESTDATA_PATH  / schema_path), schema.name])
        return subprocess.check_output(cmd, input=str(struct).encode('utf8'))
