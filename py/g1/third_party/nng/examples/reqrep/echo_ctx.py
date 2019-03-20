"""Echo server using context."""

import contextlib
import sys
import threading

import nng


def main(argv):

    if len(argv) < 3:
        print('usage: %s url num_ctxs' % argv[0], file=sys.stderr)
        return 1

    url = argv[1]
    num_ctxs = int(argv[2])

    with contextlib.ExitStack() as stack:

        socket = stack.enter_context(nng.Socket(nng.Protocols.REP0))
        socket.listen(url)

        servers = []
        for _ in range(num_ctxs):
            ctx = stack.enter_context(nng.Context(socket))
            server = threading.Thread(target=serve, args=(ctx, ))
            server.start()
            servers.append(server)

        while any(server.is_alive() for server in servers):
            try:
                for server in servers:
                    server.join()
            except KeyboardInterrupt:
                print('Keyboard interrupted!')
                nng.close_all()

    return 0


def serve(ctx):
    try:
        while True:
            data = ctx.recv()
            print('serve: %d: recv: %r' % (ctx.id, data))
            ctx.send(data)
    except nng.NngError as exc:
        print('serve: %d: nng error: %s' % (ctx.id, exc))


if __name__ == '__main__':
    sys.exit(main(sys.argv))
