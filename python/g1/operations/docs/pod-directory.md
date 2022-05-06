A pod directory is a host directory bind-mount to pod directory tree.

Pod directories are a persistent space on the host machine.  A pod
directory is accessed by the same type of pods across versions; so we
must handle concurrent access and backward/forward compatibility of the
data in pod directories.

Pod directories and volumes are not the same.  Volumes are removed when
the pod is being uninstalled, but pod directories are not.

By convention, the pod directory host path is `/srv/<pod-label>/v1`; for
example, the operations database pod directory is
`/srv/operations/database/v1`.  If we want to make a breaking change, we
increase the last path component, i.e., changing `v1` to `v2`.

In general a pod directory should grant write permission to "nobody",
who we use to run pod servers by default.

For convenience, the inside-pod path of a pod directory is made the same
as the host path.

By the way, it is preferable that pod servers can initialize an empty
pod directory during starting up (it is possible to code this in the
deployment system, but it seems to break the encapsulation of server's
implementation detail).
