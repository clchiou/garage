"""Build an image that uses CPython http.server."""

from foreman import define_parameter, define_rule, to_path
from shipyard import (
    render_appc_manifest,
    render_bundle_files,
    rsync,
)


(define_parameter('version')
 .with_doc("""Version of this build.""")
 .with_type(int)
)


(define_rule('build')
 .with_doc(__doc__)
 .depend('//base:build')
 .depend('//py/cpython:build')
)


# XXX: Unfortunately `working_directory` has to be kept in sync with
# pod.json and httpd.service, which is somewhat error-prone.
(define_rule('tapeout')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: render_appc_manifest(
     ps, '//py/cpython:templates/manifest', {'working_directory': '/var/www'}))
 .depend('build')
 .depend('//host/mako:install')
 .reverse_depend('//base:tapeout')
 .reverse_depend('//py/cpython:tapeout')
)


(define_rule('build_image')
 .with_doc("""Build containerized image.""")
 .depend('tapeout')
 .depend('//base:build_image')
)


(define_rule('build_pod')
 .with_doc("""Build deployable bundle for a pod.""")
 .with_build(lambda ps: (
     render_bundle_files(ps, [
         ('templates/%s' % name, ps['//base:output'] / name)
         for name in ('pod.json', 'httpd.service')
     ]),
     rsync([to_path('data.tgz')], ps['//base:output']),
 ))
 .depend('build_image')
 .depend('//host/mako:install')
)
