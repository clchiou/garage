## Pod rules

We want to build pods and images separately; so here is how to write pod
build rules:

* The `specify_X` kind of rules (`specify_app`, `specify_image`, and
  `specify_pod`) should **only** depend on their-own kind so that build
  tools may deduce their relationship without being bound to build them
  together.

* `write_manifest` (and maybe `build_image`) should depend on the actual
  build and tapeout rules of the packages so that when you are building
  images, correct packages are built.

* `build_pod` should **not** depend on any other rule because it is the
  rule that merely generates the pod manifest file (and thus no packages
  should be built for it).
