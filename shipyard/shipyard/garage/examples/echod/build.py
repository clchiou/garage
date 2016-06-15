"""Build echod."""

from pathlib import Path

from foreman import decorate_rule, define_parameter, define_rule, to_path
from shipyard import python_copy_and_build_package as build_pkg
from shipyard import python_copy_package as copy_pkg
from shipyard import render_template


NAME = 'echod'
PATH = 'py/garage/examples/echod'


(define_parameter('src')
 .with_doc("""Location of the source.""")
 .with_type(Path)
 .with_derive(lambda ps: ps['//base:root'] / PATH)
)


(define_parameter('version')
 .with_doc("""Version of this build.""")
 .with_type(int)
)


(define_rule('build')
 .with_doc(__doc__)
 .with_build(lambda ps: build_pkg(ps, NAME, src=ps['src']))
 .depend('//base:build')
 .depend('//cpython:build')
 .depend('//garage:build')
 .depend('//http2:build')
)


# Use generic Appc manifest at the moment.
(define_rule('tapeout')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: (
     (ps['//base:build_out'] / 'manifest').write_text(
         to_path('//cpython:manifest').read_text()),
     copy_pkg(ps, NAME),
 ))
 .depend('build')
 .reverse_depend('//base:tapeout')
 .reverse_depend('//cpython:tapeout')
)


(define_rule('build_image')
 .with_doc("""Build containerized image.""")
 .depend('tapeout')
 .depend('//base:build_image')
)


@decorate_rule('//host/mako:install')
def build_configs(parameters):
    """Build pod configs."""

    version = parameters['version']
    if version is None:
        raise RuntimeError('no version is set')

    sha512_path = parameters['//base:out'] / 'sha512'
    if not sha512_path.is_file():
        raise FileExistsError('not a file: %s' % sha512_path)

    template_vars = {
        'version': version,
        'sha512': sha512_path.read_text().strip(),
    }

    for name in ('pod.json', 'echod.service'):
        render_template(
            parameters,
            to_path('templates/%s' % name),
            parameters['//base:out'] / name,
            template_vars,
        )
