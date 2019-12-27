## Build process

The build process involves two pods: builder and application pod.

* The builder pod builds the application in-place; that is, after the
  build process completes, the builder pod will contain all application
  data, and can be used as an application pod (given that you replace
  builder pod configuration with application's).

* The application pod is builder pod without the build-time data.

To run a builder pod (and build an application image), you need two
images: base and base-extra (which are built by `bootstrap.sh`).  The
build process starts with these images, and builds application data
in-place.  After the build completes, the build process then exports the
pod overlay as the application image.

    +--------------+
    | application  | (pod overlay)
    +--------------+
    | base-extra   | (top layer)
    +--------------+
    | base         | (bottom layer)
    +--------------+

* The base image is the bare minimum that all pods require.
* The base-extra image contains extra data (such as Linux distro package
  repository) that are used in some but not all use cases.

To run the application pod, you only need two images: base and
application:

    +--------------+
    | runtime data | (pod overlay)
    +--------------+
    | application  | (top layer)
    +--------------+
    | base         | (bottom layer)
    +--------------+
