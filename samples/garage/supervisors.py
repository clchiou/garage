"""Supervisor tree example."""

import asyncio
import logging

from garage.asyncs.futures import awaiting, each_completed
from garage.asyncs.processes import process


@process
async def supervisor_proc(inbox):
    print('supervisor start')
    async with awaiting(inbox.until_closed(), cancel_on_exit=True) as stop, \
               consumer_proc() as c, \
               producer_proc(c) as p:
        async for task in each_completed([c.task, p.task], [stop]):
            await task
    print('supervisor stop')


@process
async def producer_proc(inbox, consumer):
    print('producer start')
    message = list('Hello world!')
    while message and not inbox.is_closed():
        await consumer.inbox.put(message.pop(0))
    consumer.inbox.close()
    print('producer stop')


@process
async def consumer_proc(inbox):
    print('consumer start')
    try:
        while True:
            print('consume', repr(await inbox.get()))
    finally:
        print('consumer stop')


def main():
    logging.basicConfig(level=logging.DEBUG)
    print('main start')
    supervisor = supervisor_proc()
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(supervisor.task)
    except KeyboardInterrupt:
        pass
    finally:
        supervisor.inbox.close()
        loop.run_until_complete(supervisor.task)
        loop.close()
    print('main stop')


if __name__ == '__main__':
    main()
