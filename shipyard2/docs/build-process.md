### Containerized image build process

The build process involves two pods: builder and application pod.

* The builder pod builds the application in-place; that is, after the
  build process completes, the builder pod will contain all application
  data, and can be used as an application pod (given that you replace
  builder pod configuration with application's).

* The application pod is builder pod without the build-time data.

To run a builder pod (and build an application image), you need at least
two images: base and base-builder (which are built by the bootstrap
command of the builder).  On top of that, you may use intermediate
builder images to save you time from rebuilding stuff.  The build
process starts with these images, and builds application data in-place.
After the build completes, the build process exports the pod overlay as
an intermediate builder image.

    +----------------------------------------+
    | application data                       | (pod overlay)
    +----------------------------------------+
    | intermediate builder images (optional) |
    +----------------------------------------+
    | base-builder                           |
    +----------------------------------------+
    | base                                   | (bottom layer)
    +----------------------------------------+

* The base image is the bare minimum that all pods require.
* The base-builder image contains extra data (such as Linux distro
  package repository).
* The optional intermediate builder images are application data from
  previous builds (to save time from rebuilding stuff).

To create the application image, the build process merges intermediate
builder images.

To run the application pod, you only need two images: base and
application:

    +--------------+
    | runtime data | (pod overlay)
    +--------------+
    | application  | (top layer)
    +--------------+
    | base         | (bottom layer)
    +--------------+

Open question: Should we also merge base into the application image?
For now maybe we should not; or else, we will need to tweak the default
filter rules (defined in the merge command) to work with the base image
content.
