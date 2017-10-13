"""Base part of the host-only Python environment.

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

from foreman import define_parameter, rule

from garage import scripts

from templates.common import define_distro_packages


(define_parameter.path_typed('venv')
 .with_doc("""Path to a Python venv of host-only packages.""")
 .with_derive(lambda ps: ps['//base:drydock'] / 'host/cpython/venv'))


(define_parameter.path_typed('python')
 .with_doc("""Path to the host-only Python.""")
 .with_derive(lambda ps: ps['//host/cpython:venv'] / 'bin/python3'))


(define_parameter.path_typed('pip')
 .with_doc("""Path to the host-only pip.""")
 .with_derive(lambda ps: ps['venv'] / 'bin/pip'))


define_distro_packages([
    'python3-venv',
])


@rule
@rule.depend('//base:build')
@rule.depend('install_packages')
def install(parameters):
    # NOTE: Don't use `//py/cpython:python` here since doing so would force
    # the builder to build CPython.
    venv = parameters['venv'].absolute()
    if not venv.is_dir():
        scripts.execute(['/usr/bin/python3', '-m', 'venv', '--clear', venv])
