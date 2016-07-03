"""Build echod."""

from foreman import define_parameter, define_rule
from shipyard import py
from shipyard import (
    copy_source,
    define_package_common,
    ensure_file,
    render_appc_manifest,
    render_bundle_files,
)


NAME = 'echod'
PATH = 'py/garage/examples/echod'


(define_parameter('version')
 .with_doc("""Version of this build.""")
 .with_type(int)
)


define_package_common(
    derive_src_path=lambda ps: ps['//base:root'] / PATH,
    derive_build_src_path=lambda ps: ps['//base:build_src'] / PATH,
)


(define_rule('build')
 .with_doc(__doc__)
 .with_build(lambda ps: (
     copy_source(ps['src'], ps['build_src']),
     ensure_file(ps['build_src'] / 'setup.py'),
     py.build_package(ps, NAME, ps['build_src']),
 ))
 .depend('//base:build')
 .depend('//cpython:build')
 .depend('//garage:build')
 .depend('//http2:build')
)


(define_rule('tapeout')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: (
     py.tapeout_package(ps, NAME),
     render_appc_manifest(ps, '//cpython:templates/manifest'),
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


(define_rule('build_pod')
 .with_doc("""Build deployable bundle for a pod.""")
 .with_build(lambda ps: render_bundle_files(ps, [
     ('templates/%s' % name, ps['//base:output'] / name)
     for name in ('pod.json', 'echod.service')
 ]))
 .depend('build_image')
 .depend('//host/mako:install')
)
