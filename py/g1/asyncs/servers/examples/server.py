"""Demonstrate root supervisor."""

import logging
import sys

from g1.asyncs import kernels
from g1.asyncs import servers


async def timeout_after(duration):
    kernels.timeout_after(duration)
    await kernels.Event().wait()


@kernels.with_kernel
def main(argv):
    if len(argv) != 4:
        print(
            'usage: %s grace_period sleep timeout_after' % argv[0],
            file=sys.stderr,
        )
        return 1
    logging.basicConfig(level=logging.INFO)
    server_queue = kernels.TaskCompletionQueue()
    for duration, func in ((argv[2], kernels.sleep), (argv[3], timeout_after)):
        duration = float(duration)
        if duration >= 0:
            server_queue.put(kernels.spawn(func(duration)))
    kernels.run(
        servers.supervise_servers(
            server_queue, kernels.Event(), float(argv[1])
        )
    )
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
