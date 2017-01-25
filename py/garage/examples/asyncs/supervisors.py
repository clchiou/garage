"""Supervisor tree example."""

import logging

import curio

from garage.asyncs import TaskStack
from garage.asyncs.queues import Closed, Queue


async def supervisor():
    print('supervisor start')
    async with TaskStack() as stack:
        queue = Queue()
        await stack.spawn(consumer(queue)),
        await stack.spawn(producer(queue)),
        async for task in curio.wait(stack):
            await task.join()
    print('supervisor stop')


async def producer(queue):
    print('producer start')
    message = list('Hello world!')
    while message:
        await queue.put(message.pop(0))
    queue.close()
    print('producer stop')


async def consumer(queue):
    print('consumer start')
    try:
        while True:
            print('consume', repr(await queue.get()))
    except Closed:
        pass
    finally:
        print('consumer stop')


def main():
    logging.basicConfig(level=logging.DEBUG)
    print('main start')
    try:
        curio.run(supervisor())
    except KeyboardInterrupt:
        print('main quit')
    print('main stop')


if __name__ == '__main__':
    main()
