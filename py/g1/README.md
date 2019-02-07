This is the next version of garage (the next next version will be g2, by
the way).  I decided that, instead of evolving the current garage and
maintaining backward compatibility, it is easier to just rewrite from
scratch since I am the only user of the garage.  I will deviate from g0
in g1:

* Namespace packages: The top-level package `g1` is reserved to be an
  empty namespace package.  (As a result, all `setup.py` must set
  `zip_safe` to `False`.)  And we will break down the codebase into a
  few sub-packages.  This way, we should have better modularity and
  clearer dependency within codebase.

  * But we will not go to the extreme to break every self-contained
    piece of code into a package.  Although this might be worthwhile
    when the size of garage grows very large, for now the overhead of
    fine-grained packaging seems to out weight the benefits.

* Base everything on Python 3.7: There are some environments that I am
  not running Python 3.7 at the moment, but instead of maintaining g1
  for both 3.6 and 3.7, it should be easier to upgrade all environments
  to 3.7.  This also means we should use new additions to 3.7 stdlib
  whenever possible.

* Better tests: All public functions should have at least one unit test
  exercising it (but 100% test coverage is not a goal), and test code
  should be well-structured as if it is production code (I was quite
  sloppy in writing test code).

* Linter and style checker: (I am uncertain about this one.)  All code
  should pass 100% under linter and style checker.  If not, you should
  either fix the code, tweak linter or style checker configurations, or
  (least preferable) add linter-disable marker to the code.
