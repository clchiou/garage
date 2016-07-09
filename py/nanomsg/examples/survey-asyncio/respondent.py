import asyncio
import sys

import nanomsg as nn
from nanomsg.asyncio import Socket


async def pong(url):
    with Socket(protocol=nn.NN_RESPONDENT) as sock, sock.connect(url):
        message = await sock.recv()
        print(bytes(message.as_memoryview()).decode('ascii'))
        await sock.send(b'pong')
        await asyncio.sleep(1)  # Waiting for receiving...


def main():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(asyncio.ensure_future(pong(sys.argv[1])))
    loop.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
