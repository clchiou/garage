import sys
import time

import nanomsg as nn


def ping(url):
    with nn.Socket(protocol=nn.NN_SURVEYOR) as sock, sock.bind(url):
        time.sleep(1)  # Waiting for connections...
        sock.send(b'ping')
        try:
            while True:
                message = sock.recv()
                print(bytes(message.as_memoryview()).decode('ascii'))
        except nn.NanomsgError as e:
            if e.errno is not nn.Error.ETIMEDOUT:
                raise


def main():
    ping(sys.argv[1])
    return 0


if __name__ == '__main__':
    sys.exit(main())
