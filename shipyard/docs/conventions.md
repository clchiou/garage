## Build rule template conventions

* Build rule template should be named `define_X` where `X` is the type
  of package you are defining.

* Build rule template may take an optional argument `name`, which, when
  provided, should create rule labels beneath it.  This is useful in
  avoiding rule label conflicts in one build file; for example:

    # Define `//some/package:build`.
    define_package()

    # Define `//some/package:sub-package-1/build`.
    define_package(name='sub-package-1')

    # Define `//some/package:sub-package-2/build`.
    define_package(name='sub-package-2')
