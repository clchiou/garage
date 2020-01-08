NOTE: This is evolved from the
[version 1 doc](../../shipyard/docs/release.md).

### Overview of release management

**Pod** is our unit of release.  A pod is a self-contained package of
code and data (command-line arguments, data files, etc.).

**Containerized image** is our unit of code in a release (all code in a
release are inside images), which are built in our shipyard.  A pod may
have multiple images (which are layered and will be merged into one
overlay filesystem).

**Volume** is a tarball of data files; its usage is purely optional (you
may bundle all data files into an image), but in some cases you might
want to put these data files in a volume rather than an image:
* You want to restrict access to some sensitive data files, such as
  credential files (although to be honest we do not implement any
  restriction on volume access yet).
* Somehow generation of some data files are hard to integrate with image
  build process.
* You want to save space by sharing some data files among pods.

NOTE: It is obvious that if you want to change code, you have to create
a new release for the new code, but it is less obvious that this rule
also applies to data changes.

#### Pod deployment

For now, this is very simple: To deploy a pod, you create a directory
(usually called a "bundle"), and you put all artifacts into it.  Then
you send the bundle to the target machine, and run `ctr` to install the
pod (you need extra work to launch the pod as a daemon, but that is a
different story).

In the future, we might employ a fetch-from-HTTP scheme in which you
upload all build artifacts to a HTTP server, and you only send a pod
configuration file to the target machine.  Then operations tool will
fetch the rest of bundle from the HTTP server.  This scheme could be
more efficient when you are deploying to lots of machines.

There are some platform software that are not pods, such as the
container runtime itself.  These software will be released as XARs.  For
now we re-use pod deployment tools for deploying them.

#### Environment and pod

(NOTE: In the version 1, pods are divided into channels; this design
does not seem to be useful, and is removed from this version.)

(For now we operate two environments: production and testbed, which is a
local miniature of the production environment.  Staging is a subset of
machines in an environment, not an environment.)

Ideally, a pod should be built once for all environments, but it might
not be always practical to strive for this level of generality.  For
now, we use two types of pod variant (variants share the same the pod
name, and are distinguished by version suffix):

* Same code and same static data: This is the most generic pod that can
  be executed in all environments (i.e., no variant).

* Same code but different static data: This type of pods usually has the
  code that is generic enough to be executed in all environments when
  proper configuration data is provided.

For the second type, the pod built for the production environment is
considered the canonical pod, and the pods built for other environments
are considered variants of the canonical pod and are versioned by adding
environment name, like `1.0.0-staging`.

If even the code is different under different environments, pods should
be considered different, and be assigned different names (hopefully we
can minimize the number of this type of pods).

#### Versioning convention

NOTE: This is just a convention at the moment; do not try to parse
version string in scripts.

We choose version in the form of `YY.DDD.X`, where:
* `YY` is the last two digits of the year.
* `DDD` is the day of the year, from 001 to 366.
* `X` is the patch number, from 0 to 9.

The patch number 0 is considered the base release, and whenever you want
to release a bug fix to the base release, you increment the patch number
by one.  We only reserve one digit for the patch number, but if you need
to release ten or more bug fixes, you may use more digits in the patch
number.  However, this usually indicates that you did not do enough
integration test when preparing the base release (shame on you!).

(We usually do not release more than one version per day; so using day
of the year is generally enough.)


### Management of artifacts

We have three types of artifacts that need to be managed:
* Pods.
* Containerized images.
* Data files (e.g., systemd unit files, volume data).

All three of them are versioned, and we use symlink to make references
among them.  The directory structure is:

* `envs/${ENVIRONMENT}/${LABEL_PATH}/${POD_NAME}`
  + This is a symlink to pod, representing the current version.

* `pods/${LABEL_PATH}/${POD_NAME}/${POD_VERSION}/...`
  + Release metadata: `release.json`.  This includes info like source
    code repo revision and build time.
  + Deploy instruction: `deploy.json`.  (Small data files are directly
    embedded in the deploy instruction file, by the way.)
  + Symlinks to images are under `images` directory.
  + Symlinks to volumes are under `volumes` directory.

* `images/${LABEL_PATH}/${IMAGE_NAME}/${IMAGE_VERSION}/...`
  + Image tarball: `image.tar.gz`.

* `volumes/${LABEL_PATH}/${VOLUME_NAME}/${VOLUME_VERSION}/...`
  + Volume tarball: `volume.tar.gz`.

#### Management of data input to builds

Input to builds includes code and data.  The code part is tracked and
versioned in source repos.  The data part, such as configuration files
and key files, are managed separately from the source repos.  Its
directory hierarchy is quite simple at the moment:

* `image-data/${LABEL_PATH}/${IMAGE_NAME}/...`
  Data input to image builds.

* `volume-data/${LABEL_PATH}/${VOLUME_NAME}/...`
  Data input to volume builds.
