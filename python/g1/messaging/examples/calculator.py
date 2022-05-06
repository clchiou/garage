"""Calculator client and server."""

import sys

from g1.asyncs import kernels

from examples import interfaces


async def run_server(url):
    with interfaces.make_server() as server:
        server.socket.listen(url)
        await server.serve()


async def run_client(url, op, x, y):
    with interfaces.make_client() as client:
        client.socket.dial(url)
        method = getattr(client.m, op)
        x = float(x)
        y = float(y)
        print('%s(%f, %f) == %f' % (op, x, y, await method(x=x, y=y)))


@kernels.with_kernel
def main(argv):
    if len(argv) < 3:
        print('usage: %s {client|server} url ...' % argv[0], file=sys.stderr)
        return 1
    if argv[1] == 'client' and len(argv) < 6:
        print('usage: %s client url op x y' % argv[0], file=sys.stderr)
        return 1
    if argv[1] == 'server':
        func = run_server
    else:
        func = run_client
    kernels.run(func(*argv[2:]))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
