"""Echo server using context, asynchronously."""

import contextlib
import sys

from g1.asyncs import kernels
from g1.asyncs.bases import tasks

import nng
import nng.asyncs


@kernels.with_kernel
def main(argv):
    if len(argv) < 3:
        print('usage: %s url num_ctxs' % argv[0], file=sys.stderr)
        return 1
    kernels.run(run_servers(argv[1], int(argv[2])))
    return 0


async def run_servers(url, num_ctxs):
    with contextlib.ExitStack() as stack:
        socket = stack.enter_context(nng.asyncs.Socket(nng.Protocols.REP0))
        socket.listen(url)
        async with tasks.CompletionQueue() as servers:
            for _ in range(num_ctxs):
                ctx = stack.enter_context(nng.asyncs.Context(socket))
                servers.spawn(serve(ctx))
            servers.close()
            async for server in servers:
                server.get_result_nonblocking()


async def serve(ctx):
    while True:
        data = await ctx.recv()
        print('serve: %d: recv: %r' % (ctx.id, data))
        await ctx.send(data)


if __name__ == '__main__':
    sys.exit(main(sys.argv))
