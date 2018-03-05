__all__ = [
    'pods',
]

from pathlib import Path
import json

from garage import apps

from ops import models


@apps.with_prog('read-tag')
@apps.with_help('read tag in pod file')
@apps.with_argument('pod_file', type=Path, help='provide pod file path')
def read_tag(args):
    """Read tag in pod file (useful in scripting)."""
    pod_file = args.pod_file
    if pod_file.is_dir():
        pod_file = pod_file / models.POD_JSON
    pod_data = json.loads(pod_file.read_text())
    pod = models.Pod(pod_data, pod_file.parent.absolute())
    print(pod)
    return 0


@apps.with_help('manage pods')
@apps.with_apps(
    'operation', 'operation on pods',
    read_tag,
)
def pods(args):
    """Manage containerized application pods."""
    return args.operation(args)
