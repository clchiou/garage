import asyncio
import sys

import nanomsg as nn
from nanomsg.asyncio import Socket


async def ping(url):
    with Socket(protocol=nn.NN_SURVEYOR) as sock, sock.bind(url):
        await asyncio.sleep(1)
        await sock.send(b'ping')
        try:
            while True:
                message = await sock.recv()
                print(bytes(message.as_memoryview()).decode('ascii'))
        except nn.NanomsgError as e:
            if e.errno is not nn.Error.ETIMEDOUT:
                raise


async def pong(url):
    with Socket(protocol=nn.NN_RESPONDENT) as sock, sock.connect(url):
        message = await sock.recv()
        print(bytes(message.as_memoryview()).decode('ascii'))
        await sock.send(b'pong')
        await asyncio.sleep(1)


def main():
    num_respondents = 2
    url = 'inproc://test'
    future = asyncio.wait(
        [
            asyncio.ensure_future(ping(url)),
        ] + [
            asyncio.ensure_future(pong(url))
            for _ in range(num_respondents)
        ],
        return_when=asyncio.FIRST_EXCEPTION,
    )

    loop = asyncio.get_event_loop()
    for fut in loop.run_until_complete(future)[0]:
        fut.result()
    loop.close()

    return 0


if __name__ == '__main__':
    sys.exit(main())
