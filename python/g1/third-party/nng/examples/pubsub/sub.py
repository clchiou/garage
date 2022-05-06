"""Subscribe a topic."""

import sys
import threading
import time

import nng


def main(argv):
    if len(argv) < 3:
        print('usage: %s url topic' % argv[0], file=sys.stderr)
        return 1

    def subscribe(url, topic):
        topic = topic.encode('utf-8')
        try:
            with nng.Socket(nng.Protocols.SUB0) as socket:
                socket.subscribe(topic)
                socket.dial(url)
                while True:
                    print(socket.recv().decode('utf-8'))
                    time.sleep(0.1)
        except nng.NngError as exc:
            print('serve: nng error: %s' % exc)

    # To prevent libnng blocking the Python interpreter, you should make
    # blocking calls in a thread.
    thread = threading.Thread(target=subscribe, args=argv[1:])
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
