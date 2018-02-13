## Tips

* You may reduce developer build time with "cached" builders, which
  are builder images that hold intermediate build artifacts:

    ./scripts/builder build --preserve-container ...
    docker commit -c 'CMD ["/bin/bash"]' BUILD_ID TAG

  These steps are automated:

    ./scripts/make-builder.sh \
        "${BUILDER_DOCKER_REPO}:${VERSION_TAG}" \
        "${BASE_BUILDER}" \
        --volume /path/to/local/jdk/copies:/home/plumber/input/jdk:ro \
        //meta:third-party

* You may reduce developer build time even further by disabling release
  build:

    --parameter //base:release=false

* There are meta build rules under `//meta`, which are a convenient way
  to bulk-build groups of packages.

* Run `do-build` as follows:
  ```
  scripts/do-build.sh \
    --builder-arg=--builder=builder-image \
    --builder-arg=--output=/path/to/output \
    //py/cpython:python_pod/build_pod
  ```
