"""Demonstrate ``kernels.sleep``."""

import sys
import time

from g1.asyncs import kernels


def main(argv):
    if len(argv) < 2:
        print('usage: %s duration' % argv[0], file=sys.stderr)
        return 1
    duration = float(argv[1])
    print('expect to sleep for %.3f seconds' % duration)
    start = time.perf_counter()
    kernels.run(kernels.sleep(duration))
    actual_duration = time.perf_counter() - start
    print('actually sleep for %.3f seconds' % actual_duration)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
