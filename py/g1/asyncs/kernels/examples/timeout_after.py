"""Demonstrate ``kernels.timeout_after``."""

import sys
import time

from g1.asyncs import kernels


async def do_timeout_after(duration):
    kernels.timeout_after(duration)
    try:
        await kernels.sleep(duration * 2)
    except kernels.Timeout:
        pass
    else:
        raise RuntimeError('Timeout was not raised')


def main(argv):
    if len(argv) < 2:
        print('usage: %s duration' % argv[0], file=sys.stderr)
        return 1
    duration = float(argv[1])
    print('expect to time out after %.3f seconds' % duration)
    start = time.perf_counter()
    kernels.run(do_timeout_after(duration))
    actual_duration = time.perf_counter() - start
    print('actually time out after %.3f seconds' % actual_duration)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
