"""Volume management commands."""

__all__ = [
    'COMMANDS',
]

from ops import scripting
from . import deploy
from . import models


@models.require_repo_lock
def overwrite_volumes(args, repo):
    """Overwrite deployed volumes contents."""

    # The use case of this command is complex, but basically we want to
    # do "data deploys".  Meaning that in a deployment bundle, the code
    # part is the same as a deployed pod, but only the initial contents
    # of volumes differ.  And we just want to "overwrite" the contents
    # of the deployed pod's volumes.

    pod = models.Pod.load_json(args.pod_file)
    pod_state = repo.get_pod_state(pod)
    if pod_state is models.Pod.State.UNDEPLOYED:
        raise RuntimeError('pod is not deployed yet: %s' % pod)
    if pod_state is models.Pod.State.CURRENT:
        raise RuntimeError('pod is current: %s' % pod)
    assert pod_state is models.Pod.State.DEPLOYED  # Sanity check.

    volume_root_path = repo.get_volume_path(pod)
    for volume in pod.volumes:
        if args.clear_all or volume.path or volume.uri:
            scripting.remove_tree(volume_root_path / volume.name)

    deploy.deploy_create_volumes(repo, pod, warn_on_existing_volumes=False)


overwrite_volumes.add_arguments = lambda parser: (
    models.add_arguments(parser),
    parser.add_argument(
        '--clear-all', action='store_true',
        help="""clear contents of all volumes""",
    ),
    parser.add_argument('pod_file', help="""path to a pod file"""),
)


COMMANDS = [
    overwrite_volumes,
]
