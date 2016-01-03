import ctypes
import os.path
import shutil
import tempfile
import threading
import sys

import nanomsg as nn


def ping(url):
    with nn.Socket(protocol=nn.Protocol.NN_PUSH) as sock, sock.connect(url):
        sock.send(b'Hello, World!')


def pong(url):
    with nn.Socket(protocol=nn.Protocol.NN_PULL) as sock, sock.bind(url):
        message = ctypes.create_string_buffer(16)
        size = sock.recv(message)
        print(message.raw[:size].decode('ascii'))


def main():
    path = tempfile.mkdtemp()
    try:
        url = 'ipc://' + os.path.join(path, 'reqrep.ipc')
        print('Play ping-pong on %s' % url)
        threads = [
            threading.Thread(target=ping, args=(url,)),
            threading.Thread(target=pong, args=(url,)),
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
