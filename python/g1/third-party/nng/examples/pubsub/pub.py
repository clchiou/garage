"""Publish a message."""

import itertools
import sys
import threading
import time

import nng


def main(argv):
    if len(argv) < 2:
        print('usage: %s url' % argv[0], file=sys.stderr)
        return 1

    def publish(url):
        try:
            with nng.Socket(nng.Protocols.PUB0) as socket:
                socket.listen(url)
                for i in itertools.count():
                    socket.send(b'%d' % i)
                    time.sleep(0.1)
        except nng.NngError as exc:
            print('serve: nng error: %s' % exc)

    # To prevent libnng blocking the Python interpreter, you should make
    # blocking calls in a thread.
    thread = threading.Thread(target=publish, args=argv[1:])
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
