"""Supervisor tree example."""

import asyncio
import logging

from garage.asyncs.processes import EachCompleted, Nudges, process


@process
async def supervisor_proc(inbox):
    print('supervisor start')
    async with Nudges() as nudges:
        stop = nudges.add_task(nudges.add_inbox(inbox).until_closed())
        c = nudges.add_proc(consumer_proc())
        p = nudges.add_proc(producer_proc(c))
        async for task in EachCompleted([c.task, p.task], [stop]):
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
