import asyncio
import sys

import nanomsg as nn
from nanomsg.asyncio import Socket


async def ping(url):
    with Socket(protocol=nn.NN_SURVEYOR) as sock, sock.bind(url):
        await asyncio.sleep(1)  # Waiting for connections...
        await sock.send(b'ping')
        try:
            while True:
                message = await sock.recv()
                print(bytes(message.as_memoryview()).decode('ascii'))
        except nn.NanomsgError as e:
            if e.errno is not nn.Error.ETIMEDOUT:
                raise


def main():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(asyncio.ensure_future(ping(sys.argv[1])))
    loop.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
