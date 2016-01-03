import os.path
import shutil
import tempfile
import threading
import sys

import nanomsg as nn


def ping(url, event):
    with nn.Socket(protocol=nn.Protocol.NN_PUSH) as sock, sock.connect(url):
        event.wait()
        sock.send(b'Hello, World!')


def pong(url, event):
    with nn.Socket(protocol=nn.Protocol.NN_PULL) as sock, sock.bind(url):
        event.set()
        message = sock.recv()
        print(bytes(message.as_memoryview()).decode('ascii'))


def main():
    path = tempfile.mkdtemp()
    try:
        event = threading.Event()
        url = 'ipc://' + os.path.join(path, 'reqrep.ipc')
        print('Play ping-pong on %s' % url)
        threads = [
            threading.Thread(target=ping, args=(url, event)),
            threading.Thread(target=pong, args=(url, event)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        shutil.rmtree(path)
    return 0


if __name__ == '__main__':
    sys.exit(main())
