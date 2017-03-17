## Build process

The build process itself is executed in a container as well, which we
usually refer to as a "builder", and naturally its image is referred to
as a "builder image".  To create a base builder image, you run:

  ./scripts/bootstrap TAG

### Phases of the build process

The build process consists of multiple phases:

  * Build phase: In this phase, the build process builds and installs
    all intermediate and final artifacts _locally_ within the container.
    As a result, after the build phase is completed, the builder itself,
    if exported out as an image, is a full application image.  However,
    we generally don't create an application image this way because a
    builder has all the intermediate artifacts that takes much space.

  * Tapeout phase: In this phase, we cherry-pick only build artifacts
    required in the final application image.  The resulting application
    image is much smaller than its builder's.

  * Build image phase: Packaging all build artifacts into a container
    image from the tapeout phase.

  * Build pod phase: Bundle together configuration files, static data,
    and container image(s).  Note that at the moment, a builder can only
    generate **one** image at a time, because it builds everything
    locally, and thus if a pod is composed of multiple images, you will
    have to run multiple builders.

The build phase is sequenced as:

  * `//base:build`
    All other `build` rules should depend on this rule so that this will
    be the first executed `build` rule.

  * `//your/package:build` or `//your/package:TARGET/build`
    This is the `build` rule of your package; at very minimum it should
    depend on `//base:build`.

  * `//your/package:tapeout` or `//your/package:TARGET/tapeout`
    This should depend on `//your/package:build` so that it is executed
    after its `build` rule, and reverse depend on `//base:tapeout`.

  * `//base:tapeout`
    All other `tapeout` rules should reverse depend on this rule so that
    this will be the last executed `tapeout` rule.

  * `//your/app:IMAGE/build_image`
    Build containerized application image.  Unfortunately our build
    system cannot build multiple images in one-pass because we use
    //base:tapeout as a joint point.

  * `//your/app:POD/build_pod`
    Bundle together configuration files and application image(s) into a
    pod (a tightly-coupled group of containers).
