### Overview of release management

**Pod** is our unit of release.  A pod is a self-contained package of
code and data (command-line arguments, data files, etc.).

**Containerized image** is our unit of code in a release (all code in a
release are inside images), which are built in our shipyard.  A pod may
have multiple images.

NOTE: It is obvious that if you want to change code, you have to create
a new release for the new code, but it is less obvious that this rule
applies to data changes, too.  You deploy data changes by creating a new
release.

To deploy a pod, you create a directory (usually called a "bundle"), and
you put every artifacts into it.  Then you send the bundle to the remote
machine, and run `ops-onboard` script there to deploy it.

NOTE: In the future, we might employ a fetch-from-HTTP scheme in which
you upload all build artifacts to a HTTP server, and you send only the
`pod.json` file to the remote machine.  Then `ops-onboard` tool fetches
the artifacts from the HTTP server.  This should be more efficient when
you are deploying to lots of machines.

#### Release channels

We divide pods into separate channels to simplify and isolate how an
environment gets its releases.  Also this lets us to make customizations
per environment, like adding `--verbose` to pods in staging.  But note
that in general, we prefer all channels sharing a common set of code and
data files.  See `py/ops/docs/environment.md` for more on environments.

#### Exception to the only-deploying-pods norm

There are some platform software that cannot be executed in a container,
and thus cannot be deployed as pods (a prominent example is the ops
tool).  These are an exception to the norm, and are deployed through
configuration management tool.


### Management of artifacts

We have three types of artifacts that need to be managed:
* Containerized images
* Data files (e.g., systemd unit files, volume data)
* Pods

All three of them are versioned, and we use symlink to make references
among them.  The directory structure would be like:

* `images/${LABEL_PATH}/${IMAGE_NAME}/${IMAGE_VERSION}/...`
  + `sha512`: Checksum of image.aci **before** it is compressed.
  + `image.aci`

* `volumes/${LABEL_PATH}/${VOLUME_NAME}/${VOLUME_VERSION}/...`
  + You put volume tarball files here (maybe plus metadata).

* `channels/${CHANNEL}/${LABEL_PATH}/${POD_NAME}/${POD_VERSION}/...`:
  + `pod.json`
  + It may have symlinks to images and volumes.
  + It may contain small data files.

* `channels/${CHANNEL}/${LABEL_PATH}/${POD_NAME}/tip`:
  Symlink to the latest pod.


### Release process

The process is pretty simple at the moment:
1. Create an release instruction file.
2. Run `scripts/release` script on it.

In the instruction file, you optionally specify the version of images
and volumes (both default to the pod version).  If image of that version
does not exist, the release tool will build it, but it is an error if
volume of that version does not exist (since the release tool does not
know how to create volumes).

If you put instruction files below channels directories, release tool
may infer metadata from path; for example, if its path is
`channels/.../${POD_VERSION}.yaml`, release tool may infer channel, build
rule, and version from path.

NOTE: We record source code revisions in instruction files, but at the
moment release tool does not check out specific revision prior to build.
Instead, release tool always builds from the working tree for now.
