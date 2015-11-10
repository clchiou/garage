Create thin Python app images.

1. Run `build-cpython.sh` to create a base image, which is a small
   wrapper of `docker build cpython` basically.  You may optionally
   specify the (Docker Hub) repository and the `cpython` revision you
   wish to build.

2. Now we would like to create a thin Python app image.  Start a
   container with the base image.  You might want to mount data volumes
   for source repo credentials, etc.

3. Install your Python app and all dependent Python packages for the
   `cpython` we just built from source, most likely
   `/usr/local/bin/python3.5`, *not* the system Python.
   You may use the credentials in data volumes in this step (if you need
   to fetch sources from private repos).

4. Copy build artifacts (for creating a thin image later) into a
   directory, say, `/home/rootfs`.  You may use `copy.sh` as a template.

5. Create a tarball from `/home/rootfs` and that's it.  You may copy
   that tarball file out of container for later use.

To test the tarball you just created, put it in a directory with this
Dockerfile:

    FROM scratch
    ADD rootfs.tar /
    ENTRYPOINT ["/usr/local/bin/python3"]

Then `docker build .` and then run the image.
