"""Simple web app that prints out requests."""

import json

from startup import startup

import g1.asyncs.agents.parts
import g1.http.http2_servers.parts
from g1.apps import asyncs
from g1.asyncs import kernels

LABELS = g1.http.http2_servers.parts.define_server(
    host='127.0.0.1',
    port=8000,
    reuse_address=True,
    reuse_port=True,
)


async def application(environ, start_response):
    response = environ.copy()
    response.pop('wsgi.input')
    response.pop('wsgi.errors')
    response = {
        'environ': response,
        'request_body_size': len(await environ['wsgi.input'].read()),
    }
    response = json.dumps(response, indent=4).encode('utf-8')
    start_response(
        '200 OK',
        [
            ('Content-Type', 'application/json'),
            ('Content-Length', str(len(response))),
        ],
    )
    return [response]


startup.set(LABELS.application, application)


def main(supervise_agents: g1.asyncs.agents.parts.LABELS.supervise_agents):
    kernels.run(supervise_agents)
    return 0


if __name__ == '__main__':
    asyncs.run(main)
