"""\
Base part of the host-only environment.

We adopt the build-then-cherry-pick approach, meaning that a builder
will build the final image in place, and when the build process is done,
the builder itself is a full application image.  (Unlike a cross-compile
approach in which the builder and the final application image are not
the same.)

However, this approach has its own issues; one of them is that for
Python packages that are only used by the build process, you cannot just
install them in the global Python package directory, because you cannot
later filter them out in the "cherry-pick" phase (at least not easily).

And those issues will be handled here - hopefully not many.
"""

from pathlib import Path

from foreman import define_parameter, decorate_rule
from shipyard import (
    call,
)


(define_parameter('venv')
 .with_doc("""Location of a Python venv for host-only packages.""")
 .with_type(Path)
 .with_derive(lambda ps: ps['//base:build'] / 'host/venv')
)
(define_parameter('pip')
 .with_doc("""Location of the host-only pip.""")
 .with_type(Path)
 .with_derive(lambda ps: ps['venv'] / 'bin/pip')
)


@decorate_rule('//base:build')
def install(parameters):
    """Set up host-only environment."""

    # NOTE: Don't use `//cpython:python` here since doing so would force
    # the builder to build and tape out CPython (due to corner cases of
    # reverse dependency).
    venv = str(parameters['venv'].absolute())
    call(['sudo', 'apt-get', 'install', '--yes', 'python3-venv'])
    call(['/usr/bin/python3', '-m', 'venv', '--clear', venv])
