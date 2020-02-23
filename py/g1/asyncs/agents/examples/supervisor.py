"""Demonstrate agent supervisor."""

import logging

from startup import startup

import g1.asyncs.agents.parts
from g1.apps import asyncs
from g1.asyncs import agents
from g1.asyncs import kernels
from g1.asyncs.bases import locks
from g1.asyncs.bases import timers
from g1.asyncs.kernels import errors


async def sleep(duration):
    logging.info('sleep: %f', duration)
    try:
        await timers.sleep(duration)
    except errors.TaskCancellation:
        logging.info('sleep is cancelled')
        raise


async def timeout_after(duration):
    logging.info('timeout_after: %f', duration)
    timers.timeout_after(duration)
    try:
        await locks.Event().wait()
    except errors.TaskCancellation:
        logging.info('timeout_after is cancelled')
        raise


@startup
def add_arguments(parser: asyncs.LABELS.parser) -> asyncs.LABELS.parse:
    parser.add_argument('sleep', type=float)
    parser.add_argument('timeout_after', type=float)


def main(
    args: asyncs.LABELS.args,
    agent_queue: g1.asyncs.agents.parts.LABELS.agent_queue,
    supervise_agents: g1.asyncs.agents.parts.LABELS.supervise_agents,
):
    if args.sleep >= 0:
        agent_queue.spawn(sleep(args.sleep))
    if args.timeout_after >= 0:
        agent_queue.spawn(timeout_after(args.timeout_after))
    try:
        kernels.run(supervise_agents)
    except agents.SupervisorError as exc:
        logging.error('agent supervisor err out: %r', exc)
        return 1
    return 0


if __name__ == '__main__':
    asyncs.run(main)
