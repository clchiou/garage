"""Supervisor tree example."""

import logging

import curio

from garage.asyncs.queues import Closed, Queue


async def supervisor():
    print('supervisor start')
    queue = Queue()
    tasks = [
        await curio.spawn(consumer(queue)),
        await curio.spawn(producer(queue)),
    ]
    async for task in curio.wait(tasks):
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
