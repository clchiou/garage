"""Demonstrate cluster session."""

from startup import startup

import g1.asyncs.agents.parts
import g1.http.clients.parts.clusters
import g1.threads.parts
from g1.apps import asyncs
from g1.apps import parameters
from g1.apps import utils
from g1.asyncs import kernels
from g1.asyncs.bases import tasks
from g1.bases import labels
from g1.http import clients

LABELS = labels.make_nested_labels(
    __name__,
    (
        ('session', g1.http.clients.parts.clusters.SESSION_LABEL_NAMES),
        ('stub', g1.http.clients.parts.clusters.STUB_LABEL_NAMES),
    ),
)

g1.http.clients.parts.clusters.setup_session(
    LABELS.session,
    parameters.define(
        __name__ + '.session',
        g1.http.clients.parts.clusters.make_session_params(),
    ),
)

g1.http.clients.parts.clusters.setup_stub(
    LABELS.stub,
    parameters.define(
        __name__ + '.stub',
        g1.http.clients.parts.clusters.make_stub_params(),
    ),
)

utils.bind_label(LABELS.stub.stub, LABELS.session.stubs)
utils.bind_label(
    g1.threads.parts.define_executor().executor, LABELS.session.executor
)


@startup
def add_arguments(parser: asyncs.LABELS.parser) -> asyncs.LABELS.parse:
    parser.add_argument('url', help='fetch url')


@startup
def make_agent(
    session: LABELS.session.session,
    agent_queue: g1.asyncs.agents.parts.LABELS.agent_queue,
    shutdown_queue: g1.asyncs.agents.parts.LABELS.shutdown_queue,
):
    agent_queue.spawn(session.serve)
    shutdown_queue.put_nonblocking(session.shutdown)


def main(
    args: asyncs.LABELS.args,
    stub: LABELS.stub.stub,
    supervise_agents: g1.asyncs.agents.parts.LABELS.supervise_agents,
    graceful_exit: g1.asyncs.agents.parts.LABELS.graceful_exit,
):
    supervisor_task = tasks.spawn(supervise_agents)
    request = clients.Request('GET', args.url)
    response = kernels.run(stub.send(request, priority=0))
    for link in response.html().xpath('//a'):
        print(link.get('href'))
    graceful_exit.set()
    kernels.run(supervisor_task.get_result())
    return 0


if __name__ == '__main__':
    asyncs.run(main)
