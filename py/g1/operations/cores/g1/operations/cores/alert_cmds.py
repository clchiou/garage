__all__ = [
    'main',
]

import os
from pathlib import Path

from g1.bases import argparses
from g1.bases import datetimes
from g1.bases import oses
from g1.bases.assertions import ASSERT

from . import alerts


@argparses.begin_parser(
    'set-config',
    **argparses.make_help_kwargs('copy config file'),
)
@argparses.argument(
    'path',
    type=Path,
    help='provide path to config file to be copied from',
)
@argparses.end
def cmd_set_config(args):
    oses.assert_root_privilege()
    alerts.save(alerts.load(args.path))
    return 0


@argparses.begin_parser(
    'send',
    **argparses.make_help_kwargs('send an alert'),
)
@argparses.begin_mutually_exclusive_group(required=True)
@argparses.argument(
    '--level',
    action=argparses.StoreEnumAction,
    type=alerts.Message.Levels,
    help='set message level',
)
@argparses.argument(
    '--systemd-service-result',
    metavar='RESULT',
    help='set message level by systemd service result',
)
@argparses.end
@argparses.argument(
    'title',
    help='set title',
)
@argparses.argument(
    'description',
    help='set description',
)
@argparses.end
def cmd_send(args):
    if args.systemd_service_result is not None:
        if args.systemd_service_result == 'success':
            level = alerts.Message.Levels.GOOD
        else:
            level = alerts.Message.Levels.ERROR
    else:
        level = args.level
    alerts.load().send(
        alerts.Message(
            host=os.uname().nodename,
            level=level,
            title=args.title,
            description=args.description,
            timestamp=datetimes.utcnow(),
        )
    )
    return 0


@argparses.begin_parser(
    'alerts', **argparses.make_help_kwargs('manage alerts')
)
@argparses.begin_subparsers_for_subcmds(dest='command')
@argparses.include(cmd_set_config)
@argparses.include(cmd_send)
@argparses.end
@argparses.end
def main(args):
    if args.command == 'set-config':
        return cmd_set_config(args)
    elif args.command == 'send':
        return cmd_send(args)
    else:
        return ASSERT.unreachable('unknown command: {}', args.command)
