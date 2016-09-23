"""Manage network ports allocated to pods."""

__all__ = [
    'main',
]

from ops import scripting
from ops.pods import repos


def list_ports(args):
    """List ports allocated to deployed pods."""
    repo = repos.Repo(args.ops_data)
    for port in repo.get_ports():
        print('%s:%d %s %d' %
              (port.pod_name, port.pod_version, port.name, port.port))
    return 0


list_ports.name = 'list'
list_ports.help = 'list allocated ports'


main = scripting.make_entity_main(
    prog='ops ports',
    description=__doc__,
    commands=[
        list_ports,
    ],
    use_ops_data=True,
)
