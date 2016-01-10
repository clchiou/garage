import sys

import nanomsg as nn


def pong(url):
    with nn.Socket(protocol=nn.NN_RESPONDENT) as sock, sock.connect(url):
        message = sock.recv()
        print(bytes(message.as_memoryview()).decode('ascii'))
        sock.send(b'pong')


def main():
    pong(sys.argv[1])
    return 0


if __name__ == '__main__':
    sys.exit(main())
