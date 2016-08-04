from foreman import define_parameter, define_rule
from shipyard import render_appc_manifest


(define_parameter('version')
 .with_doc("""Version of this build.""")
 .with_type(int)
)


(define_rule('build')
 .with_doc(__doc__)
 .depend('//base:build')
 .depend('//java/garage:build')
)


(define_rule('tapeout')
 .with_doc("""Copy build artifacts.""")
 .with_build(lambda ps: render_appc_manifest(
     ps,
     '//java/java:templates/manifest',
     {
         'java_home': str(ps['//java/java:java_root'] / 'jre'),
         'classpath': str(ps['//java/java:java_root'] / 'libs/garage.jar'),
     },
 ))
 .depend('build')
 .depend('//host/mako:install')
 .depend('//java/garage:tapeout')
 .reverse_depend('//base:tapeout')
 .reverse_depend('//java/java:tapeout')
)


(define_rule('build_image')
 .with_doc("""Build containerized image.""")
 .depend('tapeout')
 .depend('//base:build_image')
)
