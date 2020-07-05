__all__ = [
    'main',
    'run',
]

from startup import startup

import g1.scripts.parts
from g1.apps import bases as apps_bases
from g1.bases import argparses
from g1.bases.assertions import ASSERT

from . import alert_cmds
from . import env_cmds
from . import pod_cmds
from . import repo_cmds
from . import token_cmds
from . import xar_cmds


@argparses.begin_subparsers_for_subcmds(dest='subject')
@argparses.include(repo_cmds.main)
@argparses.include(alert_cmds.main)
@argparses.include(pod_cmds.main)
@argparses.include(xar_cmds.main)
@argparses.include(env_cmds.main)
@argparses.include(token_cmds.main)
@argparses.end
def main(args: apps_bases.LABELS.args, _: g1.scripts.parts.LABELS.setup):
    """Operations tool."""
    if args.subject == 'repos':
        return repo_cmds.main(args)
    elif args.subject == 'alerts':
        return alert_cmds.main(args)
    elif args.subject == 'pods':
        return pod_cmds.main(args)
    elif args.subject == 'xars':
        return xar_cmds.main(args)
    elif args.subject == 'envs':
        return env_cmds.main(args)
    elif args.subject == 'tokens':
        return token_cmds.main(args)
    else:
        return ASSERT.unreachable('unknown subject: {}', args.subject)


def add_arguments(parser: apps_bases.LABELS.parser) -> apps_bases.LABELS.parse:
    argparses.make_argument_parser(main, parser=parser)


def run():
    startup(add_arguments)
    apps_bases.run(main, prog='ops')
