import unittest

import threading

import nanomsg as nn


class ThreadedPipelineTest(unittest.TestCase):

    def test_pipeline(self):

        result = []

        def ping(url, ack):
            with nn.Socket(protocol=nn.NN_PUSH) as sock, sock.connect(url):
                sock.send(b'Hello, world!')
                # Shutdown the endpoint after the other side ack'ed;
                # otherwise the message could be lost.
                ack.wait()

        def pong(url, ack):
            with nn.Socket(protocol=nn.NN_PULL) as sock, sock.bind(url):
                message = sock.recv()
                result.append(bytes(message.as_memoryview()).decode('ascii'))
                ack.set()

        ack = threading.Event()
        url = 'inproc://test'
        threads = [
            threading.Thread(target=ping, args=(url, ack)),
            threading.Thread(target=pong, args=(url, ack)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(['Hello, world!'], result)


if __name__ == '__main__':
    unittest.main()
