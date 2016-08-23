from shipyard import java, pod


def make_manifest(parameters, base_manifest):
    manifest = java.make_manifest(parameters, base_manifest)
    manifest['app']['exec'].extend([
        '-classpath',
        str(parameters['//java/java:java_root'] / 'libs/garage.jar'),
        'garage.Garage',
    ])
    return manifest


pod.define_image(pod.Image(
    name='hello-world',
    make_manifest=make_manifest,
    depends=[
        '//base:tapeout',
        '//java/java:tapeout',
        '//java/garage:tapeout',
    ],
))
