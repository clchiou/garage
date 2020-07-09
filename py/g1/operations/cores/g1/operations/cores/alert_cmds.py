__all__ = [
    'main',
]

import contextlib
import logging
import logging.handlers
import os
import sys
from pathlib import Path

from g1.bases import argparses
from g1.bases import datetimes
from g1.bases import oses
from g1.bases.assertions import ASSERT
from g1.containers import models as ctr_models

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
    'watch-syslog',
    **argparses.make_help_kwargs('watch syslog'),
)
@argparses.end
def cmd_watch_syslog(args):
    del args  # Unused.
    # TODO: Check adm group rather than root.
    oses.assert_root_privilege()
    alerts.watch_syslog(alerts.load())
    return 0


@argparses.begin_parser(
    'watch-journal',
    **argparses.make_help_kwargs('watch systemd journal'),
)
@argparses.argument(
    'pod_id',
    type=ctr_models.validate_pod_id,
    help='provide pod id to watch for',
)
@argparses.end
def cmd_watch_journal(args):
    # TODO: Check adm or systemd-journal group rather than root.
    oses.assert_root_privilege()
    alerts.watch_journal(alerts.load(), args.pod_id)
    return 0


@argparses.begin_parser(
    'collectd',
    **argparses.make_help_kwargs('handle a collectd notification'),
)
@argparses.end
def cmd_collectd(args):
    del args  # Unused.
    # Although collectd documentation claims that stdout is directed to
    # /dev/null, it is a lie.  stdout/stderr are directed to pipes that
    # collected ignores.  As a result, process writing to stdout/stderr
    # will fail due to broken pipe error.
    _config_logging()
    with open(os.devnull, 'w') as devnull, \
        contextlib.redirect_stdout(devnull), \
        contextlib.redirect_stderr(devnull):
        alerts.load().send(alerts.parse_collectd_notification(sys.stdin))
    return 0


def _config_logging():
    """Remove stream handler to stdout/stderr, and add syslog handler."""
    root = logging.getLogger()
    for handler in tuple(root.handlers):
        if (
            isinstance(handler, logging.StreamHandler)
            and handler.stream in (sys.stdout, sys.stderr)
        ):
            root.removeHandler(handler)
    root.addHandler(logging.handlers.SysLogHandler(address='/dev/log'))


@argparses.begin_parser(
    'alerts', **argparses.make_help_kwargs('manage alerts')
)
@argparses.begin_subparsers_for_subcmds(dest='command')
@argparses.include(cmd_set_config)
@argparses.include(cmd_send)
@argparses.include(cmd_watch_syslog)
@argparses.include(cmd_watch_journal)
@argparses.include(cmd_collectd)
@argparses.end
@argparses.end
def main(args):
    if args.command == 'set-config':
        return cmd_set_config(args)
    elif args.command == 'send':
        return cmd_send(args)
    elif args.command == 'watch-syslog':
        return cmd_watch_syslog(args)
    elif args.command == 'watch-journal':
        return cmd_watch_journal(args)
    elif args.command == 'collectd':
        return cmd_collectd(args)
    else:
        return ASSERT.unreachable('unknown command: {}', args.command)
