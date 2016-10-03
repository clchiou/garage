"""Cap'n Proto Cython compiler plugin"""

__all__ = [
    'main',
]

import sys

from .schema import CodeGeneratorRequest


def main():
    request = CodeGeneratorRequest(sys.stdin.buffer.read())


if __name__ == '__main__':
    main()
