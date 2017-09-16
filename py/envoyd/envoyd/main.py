"""Supervise envoy processes.

It exposes a local JSON/RPC endpoint for controlling envoy processes; it
does not expose the "standard" Cap'n Proto over nanomsg at the moment
because this endpoint is expected to be used by ops script, and unlike
our "standard" servers, it does not speak Cap'n Proto over nanomsg at
the moment.
"""

__all__ = [
    'main',
]

from concurrent import futures

from garage import cli
from garage import components

from envoyd import startups

import envoyd.roles.sfp


@cli.command(startups.API_NAME)
@cli.sub_command_info('role', 'envoy role to be played')
@cli.sub_command(envoyd.roles.sfp.sfp)
@cli.defaults(make_supervisor=None)
@cli.component(startups.ControllerComponent)
def main(actors: startups.ControllerComponent.provide.actors):
    # Exit when any actor exits.
    next(futures.as_completed([actor._get_future() for actor in actors]))
