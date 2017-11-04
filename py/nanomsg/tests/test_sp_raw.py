import unittest

import curio

from nanomsg.curio import Socket
import nanomsg as nn


class SpRawTest(unittest.TestCase):

    def test_raw_server(self):

        url = 'inproc://test_sp_raw/SpRawTest/test_raw_server'

        async def client(message, expect):
            sock = Socket(domain=nn.AF_SP, protocol=nn.NN_REQ)
            async with sock, sock.connect(url):
                await sock.send(message)
                with await sock.recv() as msg:
                    actual = bytes(msg.as_memoryview())
                    self.assertEqual(expect, actual)

        async def server():
            sock = Socket(domain=nn.AF_SP_RAW, protocol=nn.NN_REP)
            async with sock, sock.bind(url):
                with await sock.recvmsg() as msg:
                    message = bytes(msg.as_memoryview())
                    message = b'hello, ' + message
                    msg.adopt_message(message, len(message), False)
                    await sock.sendmsg(msg)

        async def run():
            async with curio.TaskGroup() as group:
                await group.spawn(client(b'robot', b'hello, robot'))
                await group.spawn(server())
                await group.join()

        curio.run(run())


if __name__ == '__main__':
    unittest.main()
