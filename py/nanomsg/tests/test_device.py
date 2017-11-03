import unittest

import curio

from nanomsg.curio import Socket, device
import nanomsg as nn


class DeviceTest(unittest.TestCase):

    def test_loopback(self):

        num_clients = 5
        countdown = curio.Semaphore(1 - num_clients)

        sockets = []

        async def client(url, expect):
            try:
                async with make_sock(nn.NN_REQ) as sock, sock.connect(url):
                    await sock.send(expect)
                    with await sock.recv() as msg:
                        actual = bytes(msg.as_memoryview())
                        self.assertEqual(expect, actual)
            finally:
                await countdown.release()

        async def run_device(url):
            async with make_raw_sock(nn.NN_REP) as sock, sock.bind(url):
                sockets.append(sock)
                await device(sock)

        async def run():
            async with curio.TaskGroup() as group:
                for i in range(num_clients):
                    await group.spawn(client('inproc://loopback', b'%d' % i)),
                await group.spawn(run_device('inproc://loopback'))
                await group.spawn(close_sockets(countdown, sockets))
                await group.join()

        curio.run(run())

    def test_reqrep(self):

        num_clients = 5
        countdown = curio.Semaphore(1 - num_clients)

        sockets = []

        async def client(url, expect):
            try:
                async with make_sock(nn.NN_REQ) as sock, sock.connect(url):
                    await sock.send(expect)
                    with await sock.recv() as msg:
                        actual = bytes(msg.as_memoryview())
                        self.assertEqual(expect, actual)
            finally:
                await countdown.release()

        async def server(url):
            async with make_sock(nn.NN_REP) as sock, sock.connect(url):
                sockets.append(sock)
                while True:
                    try:
                        with await sock.recv() as msg:
                            await sock.send(bytes(msg.as_memoryview()))
                    except nn.EBADF:
                        break

        async def run_device(url1, url2):
            async with \
                    make_raw_sock(nn.NN_REP) as sock1, sock1.bind(url1), \
                    make_raw_sock(nn.NN_REQ) as sock2, sock2.bind(url2):
                sockets.append(sock1)
                sockets.append(sock2)
                await device(sock1, sock2)

        async def run():
            async with curio.TaskGroup() as group:
                for i in range(num_clients):
                    await group.spawn(client('inproc://frontend', b'%d' % i)),
                await group.spawn(server('inproc://backend'))
                await group.spawn(run_device(
                    'inproc://frontend',
                    'inproc://backend',
                ))
                await group.spawn(close_sockets(countdown, sockets))
                await group.join()

        curio.run(run())

    def test_pipeline(self):

        num_clients = 5
        countdown = curio.Semaphore(1 - num_clients)

        done = curio.Event()

        sockets = []

        actual = set()

        async def client(url, data):
            async with make_sock(nn.NN_PUSH) as sock, sock.connect(url):
                await sock.send(data)
                await done.wait()

        async def server(url):
            async with make_sock(nn.NN_PULL) as sock, sock.connect(url):
                sockets.append(sock)
                try:
                    while True:
                        try:
                            with await sock.recv() as msg:
                                actual.add(bytes(msg.as_memoryview()))
                                await countdown.release()
                        except nn.EBADF:
                            break
                finally:
                    await done.set()

        async def run_device(url1, url2):
            async with \
                    make_raw_sock(nn.NN_PULL) as sock1, sock1.bind(url1), \
                    make_raw_sock(nn.NN_PUSH) as sock2, sock2.bind(url2):
                sockets.append(sock1)
                sockets.append(sock2)
                await device(sock1, sock2)

        async def run():
            async with curio.TaskGroup() as group:
                for i in range(num_clients):
                    await group.spawn(client('inproc://frontend', b'%d' % i)),
                await group.spawn(server('inproc://backend'))
                await group.spawn(run_device(
                    'inproc://frontend',
                    'inproc://backend',
                ))
                await group.spawn(close_sockets(countdown, sockets))
                await group.join()
                self.assertEqual(
                    {b'%d' % i for i in range(num_clients)},
                    actual,
                )

        curio.run(run())


def make_sock(protocol):
    return Socket(domain=nn.AF_SP, protocol=protocol)


def make_raw_sock(protocol):
    return Socket(domain=nn.AF_SP_RAW, protocol=protocol)


async def close_sockets(countdown, sockets):
    await countdown.acquire()
    for sock in sockets:
        sock.close()


if __name__ == '__main__':
    unittest.main()
