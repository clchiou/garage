"""Calculator client using parts."""

from startup import startup

import g1.messaging.parts.clients
from g1.apps import asyncs
from g1.asyncs import kernels

from examples import interfaces

LABELS = g1.messaging.parts.clients.define_client()

startup.add_func(interfaces.make_client, {'return': LABELS.client})


@startup
def add_arguments(parser: asyncs.LABELS.parser) -> asyncs.LABELS.parse:
    parser.add_argument('op', choices=('add', 'sub', 'mul', 'div'))
    parser.add_argument('x', type=float)
    parser.add_argument('y', type=float)


async def calculate(client, op, x, y):
    method = getattr(client.m, op)
    print('%s(%f, %f) == %f' % (op, x, y, await method(x=x, y=y)))


def main(args: asyncs.LABELS.args, client: LABELS.client):
    kernels.run(calculate(client, args.op, args.x, args.y))
    return 0


if __name__ == '__main__':
    asyncs.run(main)
