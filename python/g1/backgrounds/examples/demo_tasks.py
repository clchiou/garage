"""Demonstrate background asynchronous tasks."""

import g1.asyncs.agents.parts
import g1.backgrounds.tasks
from g1.apps import asyncs
from g1.asyncs import kernels
from g1.asyncs.bases import timers


async def raises():
    raise Exception('Boom!')


async def sleep_forever():
    while True:
        try:
            await timers.sleep(None)
        except BaseException as exc:
            # Block even when this task get cancelled.
            print('catch exception: %r' % exc)


async def do_exit(graceful_exit):
    await timers.sleep(0.1)
    graceful_exit.set()


def main(
    queue: g1.backgrounds.tasks.LABELS.queue,
    supervise_agents: g1.asyncs.agents.parts.LABELS.supervise_agents,
    graceful_exit: g1.asyncs.agents.parts.LABELS.graceful_exit,
):
    queue.spawn(sleep_forever)
    queue.spawn(raises)
    queue.spawn(do_exit(graceful_exit))
    kernels.run(supervise_agents)
    return 0


if __name__ == '__main__':
    asyncs.run(main)
