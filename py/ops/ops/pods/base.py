"""Base set of commands."""

__all__ = [
    'list_pods',
    'is_deployed',
]

from ops.pods import repos


def list_pods(args):
    """List deployed pods."""
    repo = repos.Repo(args.ops_data)
    for name in repo.get_all_pod_names():
        for pod in repo.iter_pods_from_name(name):
            print(pod)
    return 0


list_pods.name = 'list'
list_pods.help = 'list deployed pods'


def is_deployed(args):
    """Check if pod is deployed."""
    repo = repos.Repo(args.ops_data)
    if repo.is_pod_deployed(args.tag):
        return 0
    else:
        return 1


is_deployed.help = 'check if pod is deployed'
is_deployed.add_arguments_to = lambda parser: (
    parser.add_argument('tag', help="""pod tag of the form 'name:version'"""),
)
