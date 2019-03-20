"""Forward messages."""

import contextlib
import sys

from g1.asyncs import kernels
from g1.asyncs.bases import tasks

import nng
import nng.asyncs


@kernels.with_kernel
def main(argv):

    if len(argv) < 3:
        print('usage: %s rep_url req_url' % argv[0], file=sys.stderr)
        return 1

    async def serve():
        async with contextlib.AsyncExitStack() as stack:
            rep_socket = stack.enter_context(
                nng.asyncs.Socket(nng.Protocols.REP0, raw=True)
            )
            rep_socket.listen(argv[1])
            req_socket = stack.enter_context(
                nng.asyncs.Socket(nng.Protocols.REQ0, raw=True)
            )
            req_socket.dial(argv[2])
            queue = await stack.enter_async_context(tasks.CompletionQueue())
            queue.spawn(forward('->', rep_socket, req_socket))
            queue.spawn(forward('<-', req_socket, rep_socket))
            queue.close()
            async for task in queue:
                task.get_result_nonblocking()

    async def forward(name, sock0, sock1):
        while True:
            await sock1.sendmsg(await sock0.recvmsg())
            print('%s: forward one message' % name)

    kernels.run(serve)

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
