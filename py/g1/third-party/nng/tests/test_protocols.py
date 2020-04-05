import unittest

import contextlib
import uuid

try:
    from g1.devtools import tests
except ImportError:
    tests = None

import nng
from nng import sockets


def _send(sock, data):
    tests.spawn(sock.send, data).result()


def _recv(sock):
    return tests.spawn(sock.recv).result()


@unittest.skipUnless(tests, 'g1.tests unavailable')
class ProtocolsTest(unittest.TestCase):

    def test_bus0(self):
        with contextlib.ExitStack() as stack:
            url = 'inproc://%s' % uuid.uuid4()
            s1 = stack.enter_context(sockets.Socket(nng.Protocols.BUS0))
            s2 = stack.enter_context(sockets.Socket(nng.Protocols.BUS0))
            s3 = stack.enter_context(sockets.Socket(nng.Protocols.BUS0))
            s1.listen(url)
            s2.dial(url)
            s3.dial(url)
            _send(s1, b'hello world')
            self.assertEqual(_recv(s2), b'hello world')
            self.assertEqual(_recv(s3), b'hello world')

    def test_pair0(self):
        with contextlib.ExitStack() as stack:
            url = 'inproc://%s' % uuid.uuid4()
            s1 = stack.enter_context(sockets.Socket(nng.Protocols.PAIR0))
            s2 = stack.enter_context(sockets.Socket(nng.Protocols.PAIR0))
            s1.listen(url)
            s2.dial(url)
            _send(s1, b'hello world')
            self.assertEqual(_recv(s2), b'hello world')
            _send(s2, b'foo bar')
            self.assertEqual(_recv(s1), b'foo bar')

    def test_pair1(self):
        with contextlib.ExitStack() as stack:
            url = 'inproc://%s' % uuid.uuid4()
            s1 = stack.enter_context(sockets.Socket(nng.Protocols.PAIR1))
            s2 = stack.enter_context(sockets.Socket(nng.Protocols.PAIR1))
            s3 = stack.enter_context(sockets.Socket(nng.Protocols.PAIR1))
            s1.polyamorous = True
            s1.listen(url)
            s2.dial(url)
            s3.dial(url)
            _send(s2, b'hello world')
            _send(s3, b'foo bar')
            self.assertEqual(
                sorted([_recv(s1), _recv(s1)]),
                [b'foo bar', b'hello world'],
            )

    def test_pubsub0(self):
        with contextlib.ExitStack() as stack:
            url = 'inproc://%s' % uuid.uuid4()
            s1 = stack.enter_context(sockets.Socket(nng.Protocols.PUB0))
            s2 = stack.enter_context(sockets.Socket(nng.Protocols.SUB0))
            s3 = stack.enter_context(sockets.Socket(nng.Protocols.SUB0))
            s1.listen(url)
            s2.dial(url)
            s3.dial(url)
            s2.subscribe(b'')
            s3.subscribe(b'')
            _send(s1, b'hello world')
            self.assertEqual(_recv(s2), b'hello world')
            self.assertEqual(_recv(s3), b'hello world')

    def test_reqrep0(self):
        with contextlib.ExitStack() as stack:
            url = 'inproc://%s' % uuid.uuid4()
            s1 = stack.enter_context(sockets.Socket(nng.Protocols.REP0))
            s2 = stack.enter_context(sockets.Socket(nng.Protocols.REQ0))
            s1.listen(url)
            s2.dial(url)
            _send(s2, b'hello world')
            self.assertEqual(_recv(s1), b'hello world')
            _send(s1, b'foo bar')
            self.assertEqual(_recv(s2), b'foo bar')

    def test_survey0(self):
        with contextlib.ExitStack() as stack:
            url = 'inproc://%s' % uuid.uuid4()
            s1 = stack.enter_context(sockets.Socket(nng.Protocols.SURVEYOR0))
            s2 = stack.enter_context(sockets.Socket(nng.Protocols.RESPONDENT0))
            s3 = stack.enter_context(sockets.Socket(nng.Protocols.RESPONDENT0))
            s1.listen(url)
            s2.dial(url)
            s3.dial(url)
            _send(s1, b'hello world')
            self.assertEqual(_recv(s2), b'hello world')
            self.assertEqual(_recv(s3), b'hello world')
            _send(s2, b'spam')
            _send(s3, b'egg')
            self.assertEqual(sorted([_recv(s1), _recv(s1)]), [b'egg', b'spam'])


if __name__ == '__main__':
    unittest.main()
