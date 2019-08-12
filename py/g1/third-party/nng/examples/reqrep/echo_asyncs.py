"""Echo a request, asynchronously."""

import sys

from g1.asyncs import kernels

import nng
import nng.asyncs


@kernels.with_kernel
def main(argv):

    if len(argv) < 3:
        print('usage: %s {client|server} url ...' % argv[0], file=sys.stderr)
        return 1
    if argv[1] == 'client' and len(argv) < 4:
        print('usage: %s client url request' % argv[0], file=sys.stderr)
        return 1

    async def serve():
        with nng.asyncs.Socket(nng.Protocols.REP0) as socket:
            socket.listen(argv[2])
            while True:
                data = await socket.recv()
                print('serve: recv: %r' % data)
                await socket.send(data)

    async def request():
        with nng.asyncs.Socket(nng.Protocols.REQ0) as socket:
            socket.dial(argv[2])
            await socket.send(argv[3].encode('utf8'))
            print((await socket.recv()).decode('utf8'))

    target = request if argv[1] == 'client' else serve
    kernels.run(target)

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
