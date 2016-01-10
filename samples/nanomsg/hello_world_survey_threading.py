import sys
import threading
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


def pong(url):
    with nn.Socket(protocol=nn.NN_RESPONDENT) as sock, sock.connect(url):
        message = sock.recv()
        print(bytes(message.as_memoryview()).decode('ascii'))
        sock.send(b'pong')
        time.sleep(1)  # Waiting for receiving...


def main():
    num_respondents = 2
    url = 'inproc://test'
    threads = [
        threading.Thread(target=ping, args=(url,))
    ] + [
        threading.Thread(target=pong, args=(url,))
        for _ in range(num_respondents)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return 0


if __name__ == '__main__':
    sys.exit(main())
