"""Demonstrate ``g1.apps.bases``."""

from g1.apps import bases


def main(args: bases.LABELS.args):
    print(args)
    return 0


if __name__ == '__main__':
    bases.run(main)
