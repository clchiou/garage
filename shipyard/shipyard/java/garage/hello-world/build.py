from shipyard import pod


pod.define_image(pod.Image(
    name='hello-world',
    manifest='//java/java:templates/manifest',
    make_template_vars=lambda ps: {
        'java_home': str(ps['//java/java:java_root'] / 'jre'),
        'classpath': str(ps['//java/java:java_root'] / 'libs/garage.jar'),
    },
    depends=[
        '//base:tapeout',
        '//java/garage:tapeout',
    ],
))
