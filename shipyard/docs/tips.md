## Tips

* You may reduce developer build time with "cached" builders, which
  are builder images that hold intermediate build artifacts:

    ./scripts/builder build --preserve-container ...
    docker commit -c 'CMD ["/bin/bash"]' BUILD_ID TAG

  These steps are automated:

    ./scripts/do-make-builder.sh \
        "${BUILDER_DOCKER_REPO}:${VERSION_TAG}" \
        "${BASE_BUILDER}" \
        "/path/to/local/warehouse"

* There are meta build rules under `//meta`, which are a convenient way
  to bulk-build groups of packages.

* You may use this to recursively list a Python package's dependencies:
    pip3 download --dest /tmp --no-binary :all: package==version
