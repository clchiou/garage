"""Demonstrate ``g1.apps.asyncs``."""

import g1.asyncs.kernels.contexts
from g1.apps import asyncs


def main(args: asyncs.LABELS.args):
    print(args)
    print(g1.asyncs.kernels.get_kernel())
    return 0


if __name__ == '__main__':
    asyncs.run(main)
