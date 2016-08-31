from shipyard import java, pod


java.define_package(
    package_name='garage',
)


def make_manifest(parameters, manifest):
    manifest = java.make_manifest(parameters, manifest)
    classpath = str(parameters['//java/java:java_root'] / 'libs/garage.jar')
    manifest['app']['exec'].extend(['-classpath', classpath, 'garage.Garage'])
    return manifest


pod.define_image(pod.Image(
    name='garage',
    make_manifest=make_manifest,
    depends=[
        '//base:tapeout',
        '//java/java:tapeout',
        '//java/garage:tapeout',
    ],
))
