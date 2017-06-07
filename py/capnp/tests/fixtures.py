__all__ = [
    'Fixture',
]

from pathlib import Path
import subprocess
import unittest


class Fixture(unittest.TestCase):

    TESTDATA_PATH = Path(__file__).parent / 'testdata'

    @classmethod
    def compile(cls, path):
        """Compile schema file in testdata/ directory."""
        return subprocess.check_output([
            'capnp', 'compile', '-o-', str(cls.TESTDATA_PATH  / path),
        ])
