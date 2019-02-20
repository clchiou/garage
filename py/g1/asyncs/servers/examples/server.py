"""Demonstrate root supervisor."""

import logging
import sys

from g1.asyncs import kernels
from g1.asyncs import servers
from g1.asyncs.bases import locks
from g1.asyncs.bases import tasks
from g1.asyncs.bases import timers


async def timeout_after(duration):
    timers.timeout_after(duration)
    await locks.Event().wait()


@kernels.with_kernel
def main(argv):
    if len(argv) != 4:
        print(
            'usage: %s grace_period sleep timeout_after' % argv[0],
            file=sys.stderr,
        )
        return 1
    logging.basicConfig(level=logging.INFO)
    server_queue = tasks.CompletionQueue()
    for duration, func in ((argv[2], timers.sleep), (argv[3], timeout_after)):
        duration = float(duration)
        if duration >= 0:
            server_queue.spawn(func(duration))
    kernels.run(
        servers.supervise_servers(server_queue, locks.Event(), float(argv[1]))
    )
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
