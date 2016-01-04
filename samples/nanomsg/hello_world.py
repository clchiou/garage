import threading
import sys

import nanomsg as nn


def ping(url, barrier):
    with nn.Socket(protocol=nn.NN_PUSH) as sock, sock.connect(url):
        sock.send(b'Hello, World!')
        # Shutdown the endpoint after the other side ack'ed; otherwise
        # the message could be lost.
        barrier.wait()


def pong(url, barrier):
    with nn.Socket(protocol=nn.NN_PULL) as sock, sock.bind(url):
        message = sock.recv()
        print(bytes(message.as_memoryview()).decode('ascii'))
        barrier.wait()


def main():
    barrier = threading.Barrier(2)
    url = 'inproc://test'
    print('Play ping-pong on %s' % url)
    threads = [
        threading.Thread(target=ping, args=(url, barrier)),
        threading.Thread(target=pong, args=(url, barrier)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return 0


if __name__ == '__main__':
    sys.exit(main())
