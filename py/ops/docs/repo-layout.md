## Directory layout of pod repos

Everything is stored under `/var/lib/ops` (this path is configurable
from command-line), which is called the root directory of all repos.
Each repo directory under the root directory is versioned; for example,
version 1 will be at path `/var/lib/ops/v1`.  This offers us a migration
path to a new version of repo layout.

Every pod is stored in `${REPO}/pods/${NAME}/${VERSION}` and inside it
the layout is:

* `pod.json` describes everything about the pod.

* `pod-manifest.json` is the generated Appc pod manifest, in case you
  want to launch a pod without providing systemd units.
* `pod-manifests/${UNIT_NAME}.json` is the generated Appc pod manifest
  for each unit instance.

* `images/${NAME}.aci` are Appc images.

* `systemd/...` are systemd unit files.

* `volumes/${NAME}` are (extracted) container volumes.

* `volume-data/${NAME}` are initial contents of volumes.
