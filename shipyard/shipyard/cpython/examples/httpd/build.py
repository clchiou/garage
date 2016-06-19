"""Build an image that uses CPython http.server."""

from foreman import decorate_rule, define_parameter, define_rule, to_path
from shipyard import render_template, rsync


(define_parameter('version')
 .with_doc("""Version of this build.""")
 .with_type(int)
)


(define_rule('build')
 .with_doc(__doc__)
 .depend('//base:build')
 .depend('//cpython:build')
)


# Use generic Appc manifest at the moment.
(define_rule('tapeout')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: (
     (ps['//base:build_out'] / 'manifest').write_text(
         to_path('//cpython:manifest').read_text()),
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

    sha512_path = parameters['//base:output'] / 'sha512'
    if not sha512_path.is_file():
        raise FileExistsError('not a file: %s' % sha512_path)

    template_vars = {
        'version': version,
        'sha512': sha512_path.read_text().strip(),
    }

    for name in ('pod.json', 'httpd.service'):
        render_template(
            parameters,
            to_path('templates/%s' % name),
            parameters['//base:output'] / name,
            template_vars,
        )

    rsync([to_path('data.tgz')], parameters['//base:output'])
