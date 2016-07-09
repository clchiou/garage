"""Supervisor tree example."""

import asyncio
import logging

from garage.asyncs.futures import awaiting, on_exit, each_completed, one_of
from garage.asyncs.processes import process
from garage.asyncs.queues import Closed, Queue


@process
async def supervisor(exit):
    print('supervisor start')
    queue = Queue()
    async with awaiting(consumer(queue)) as consumer_, \
               awaiting(producer(queue)) as producer_, \
               on_exit(consumer_.stop), \
               on_exit(producer_.stop):
        async for task in each_completed([consumer_, producer_], [exit]):
            await task
    print('supervisor stop')


@process
async def producer(exit, queue):
    async def put(item):
        await one_of([queue.put(item)], [exit])
    print('producer start')
    message = list('Hello world!')
    while message:
        await put(message.pop(0))
    queue.close()
    print('producer stop')


@process
async def consumer(exit, queue):
    async def get():
        return await one_of([queue.get()], [exit])
    print('consumer start')
    try:
        while True:
            print('consume', repr(await get()))
    except Closed:
        pass
    finally:
        print('consumer stop')


def main():
    logging.basicConfig(level=logging.DEBUG)
    print('main start')
    supervisor_ = supervisor()
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(supervisor_)
    except KeyboardInterrupt:
        pass
    finally:
        supervisor_.stop()
        loop.run_until_complete(supervisor_)
        loop.close()
    print('main stop')


if __name__ == '__main__':
    main()
