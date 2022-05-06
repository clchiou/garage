"""Demonstrate ``recvfile``."""

from startup import startup

from g1.apps import asyncs
from g1.apps import utils
from g1.asyncs import kernels
from g1.http import clients

import g1.http.clients.parts
import g1.threads.parts

LABELS = g1.http.clients.parts.define_session()

utils.bind_label(
    g1.threads.parts.define_executor().executor,
    LABELS.executor,
)


@startup
def add_arguments(parser: asyncs.LABELS.parser) -> asyncs.LABELS.parse:
    parser.add_argument('url', help='fetch url')
    parser.add_argument('output', help='output file path')


def main(args: asyncs.LABELS.args, session: LABELS.session):
    request = clients.Request('GET', args.url)
    with kernels.run(session.send(request, stream=True)) as response:
        with open(args.output, 'wb') as f:
            kernels.run(response.recvfile(f))
    return 0


if __name__ == '__main__':
    asyncs.run(main)
