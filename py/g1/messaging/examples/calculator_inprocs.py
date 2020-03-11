"""Calculator in-proc server using parts."""

from startup import startup

import g1.messaging.parts.inprocs
from g1.apps import asyncs
from g1.asyncs import kernels

from examples import interfaces

LABELS = g1.messaging.parts.inprocs.define_server()

startup.add_func(interfaces.make_inproc_server, {'return': LABELS.server})


@startup
def add_arguments(parser: asyncs.LABELS.parser) -> asyncs.LABELS.parse:
    parser.add_argument('op', choices=('add', 'sub', 'mul', 'div'))
    parser.add_argument('x', type=float)
    parser.add_argument('y', type=float)


async def calculate(server, op, x, y):
    method = getattr(server.m, op)
    print('%s(%f, %f) == %f' % (op, x, y, await method(x=x, y=y)))


def main(args: asyncs.LABELS.args, server: LABELS.server):
    kernels.run(calculate(server, args.op, args.x, args.y))
    return 0


if __name__ == '__main__':
    asyncs.run(main)
