"""Build echod."""

from pathlib import Path

from foreman import define_parameter, define_rule
from shipyard import python_copy_and_build_package as build_pkg
from shipyard import python_copy_package as copy_pkg
from shipyard import (
    render_appc_manifest,
    render_bundle_files,
)


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


(define_rule('tapeout')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: (
     render_appc_manifest(ps, '//cpython:templates/manifest'),
     copy_pkg(ps, NAME),
 ))
 .depend('build')
 .depend('//host/mako:install')
 .reverse_depend('//base:tapeout')
 .reverse_depend('//cpython:tapeout')
)


(define_rule('build_image')
 .with_doc("""Build containerized image.""")
 .depend('tapeout')
 .depend('//base:build_image')
)


(define_rule('build_configs')
 .with_doc("""Build pod configs.""")
 .with_build(lambda ps: render_bundle_files(ps, [
     ('templates/%s' % name, ps['//base:output'] / name)
     for name in ('pod.json', 'echod.service')
 ]))
 .depend('//host/mako:install')
)
