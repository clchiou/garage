"""Manage containerized application pods."""

__all__ = [
    'main',
]

from ops import scripting
from ops.pods import base, deploy


main = scripting.make_entity_main(
    prog='ops pods',
    description=__doc__,
    commands=[
        base.list_pods,
        base.is_deployed,
        base.read_tag,
        base.make_manifest,
        deploy.deploy,
        deploy.start,
        deploy.stop,
        deploy.undeploy,
        deploy.cleanup,
    ],
)
