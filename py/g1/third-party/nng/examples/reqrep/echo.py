"""Echo a request."""

import sys
import threading

import nng


def main(argv):

    if len(argv) < 3:
        print('usage: %s {client|server} url ...' % argv[0], file=sys.stderr)
        return 1
    if argv[1] == 'client' and len(argv) < 4:
        print('usage: %s client url request' % argv[0], file=sys.stderr)
        return 1

    def serve():
        try:
            with nng.Socket(nng.Protocols.REP0) as socket:
                print(
                    f'name={socket.name!r}\n'
                    f'protocol_name={socket.protocol_name!r}\n'
                    f'max_recv_size={socket.max_recv_size!r}\n'
                    f'min_reconnect_time={socket.min_reconnect_time!r}\n'
                    f'max_reconnect_time={socket.max_reconnect_time!r}\n',
                    end='',
                )
                socket.listen(argv[2])
                while True:
                    data = socket.recv()
                    print('serve: recv: %r' % data)
                    socket.send(data)
        except nng.NngError as exc:
            print('serve: nng error: %s' % exc)

    def request():
        try:
            with nng.Socket(nng.Protocols.REQ0) as socket:
                socket.dial(argv[2])
                socket.send(argv[3].encode('utf8'))
                print(socket.recv().decode('utf8'))
        except nng.NngError as exc:
            print('request: nng error: %s' % exc)

    target = request if argv[1] == 'client' else serve

    # To prevent libnng blocking the Python interpreter, you should make
    # blocking calls in a thread.
    thread = threading.Thread(target=target)
    thread.start()
    while thread.is_alive():
        try:
            thread.join()
        except KeyboardInterrupt:
            print('Keyboard interrupted!')
            nng.close_all()

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
