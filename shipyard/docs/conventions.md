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

* All build rules should transitively depend on `//base:build` (except
  `//base:build` itself of course).

* Build rule template should return the build rule objects it creates so
  that its caller has a chance to refine the rule objects.

* First-party build rule template may take an optional argument `root`,
  which, when provided, is a parameter name that overrides the default
  parameter `//base:root`.

* Build rule name should be a verb, like `build` or `upgrade`.
