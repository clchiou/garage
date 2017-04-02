__all__ = [
    'pods',
]

from pathlib import Path
import json

from garage import cli
from garage.components import ARGS

from ops import models


@cli.command('read-tag', help='read tag in pod file')
@cli.argument('pod_file', type=Path, help='provide pod file path')
def read_tag(args: ARGS):
    """Read tag in pod file (useful in scripting)."""
    pod_file = args.pod_file
    if pod_file.is_dir():
        pod_file = pod_file / models.POD_JSON
    pod_data = json.loads(pod_file.read_text())
    pod = models.Pod(pod_data, pod_file.parent.absolute())
    print(pod)
    return 0


@cli.command(help='manage pods')
@cli.sub_command_info('operation', 'operation on pods')
@cli.sub_command(read_tag)
def pods(args: ARGS):
    """Manage containerized application pods."""
    return args.operation()
