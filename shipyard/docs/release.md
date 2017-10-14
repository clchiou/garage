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
environment gets its releases.

#### Environment and pod

Ideally, a pod should be built once for all environments, but it is not
always practical to strive for this level of generality.

For now, we use two types of pod variant (variants share the same the
pod name, and are distinguished by version suffix):

* Same image and same volumes: this is the most generic pod that can be
  executed in all environments (i.e., no variant).

* Same image but different volumes: note that images are the "code" part
  of a pod and volumes are the "data" part.  This type of pods basically
  has the code that is generic enough to be executed in all environments
  if proper input data is provided.

For the second type, the pod built for the production environment is
considered the canonical pod, and the pods built for other environments
are considered variants of the canonical pod and are versioned by adding
environment name, like `1.0.0-staging`.

If even the images are different, pods will be considered different, and
be assigned different names (hopefully we can minimize the number of
this type of pods).

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
among them.  The directory structure is:

* `images/${LABEL_PATH}/${IMAGE_NAME}/${IMAGE_VERSION}/...`
  + `sha512`: Checksum of `image.aci` **before** it is compressed.
  + `image.aci`

* `volumes/${LABEL_PATH}/${VOLUME_NAME}/${VOLUME_VERSION}/...`
  + You put volume tarball files here (maybe plus metadata).

* `pods/${LABEL_PATH}/${POD_NAME}/${POD_VERSION}/...`
  + `pod.json`
  + It may have symlinks to images and volumes.
  + It may contain small data files.

* `channels/${CHANNEL}/${LABEL_PATH}/${POD_NAME}`:
  + Symlink to pod (represent the current version of this pod).


### Release process

The process is pretty simple at the moment:
1. Create an release instruction file.
2. Run `scripts/release build` script on it.

In the instruction file, you optionally specify the version of images
and volumes (both default to the pod version).  If image of that version
does not exist, the release tool will build it, but it is an error if
volume of that version does not exist (since the release tool does not
know how to create volumes).

If you put instruction files below pods directories, release tool may
infer metadata encoded in path.

NOTE: We record source code revisions in instruction files, but at the
moment release tool does not check out specific revision prior to build.
Instead, release tool always builds from the working tree for now.

A release instruction looks like this:
```
---
# Store this at `pods/py/cpython/python/3.6.yaml` and release
# tool may deduce label path and pod name.

# Rule to build this pod (note that rule name prefix "python_pod"
# differs from the name of the pod "python" - they don't need to be the
# same).
rule: python_pod/build_pod

# This is usually not necessary since release tool will deduce the
# correct images to build from the pod rule (note: this is not the
# `build_image` rule, but is the label that refers to the image under
# the `images` directory).
# images:
#   "//some/package:image_name": image_version

# Also, release tool will deduce volumes from the build rule, but
# occasionally you may want to include data volumes as well.  Note that
# the labels here refer to files under the `volumes` directory, not to
# files in the shipyard.
#
# NOTE: This may feel strange, but if the volume is mapped, you should
# put the map-from volume here, not map-to volume; for example, if
# //package:volume is mapped to //staging-package:staging-volume, you
# should put //package:volume here.
#
# volumes:
#   "//some/package:volume_name": volume_version

# You may specify parameters as well.
# parameters:
#  "//some/package:parameter_name": parameter_value
```

You may generate a release instruction with this command:
```
scripts/release \
  --release-root /path/to/releases \
  gen-inst \
  //py/cpython:python@3.6 \
  //py/cpython:python_pod/build_pod
```

Then you may build it with:
```
scripts/release \
  --release-root /path/to/releases \
  build \
  --builder-arg=--builder=builder-image \
  //py/cpython:python@3.6
```

NOTE: In build files, `name` attribute of `pods.Image` and `pods.Volume`
are used as symlink name in the pod directory; so be careful as you
should avoid any name conflicts between the two.

(By the way, because `volume.name` is used as symlink file name, the
`volume.data` attribute, which is a path, will usually start with
`volume.name`.)
