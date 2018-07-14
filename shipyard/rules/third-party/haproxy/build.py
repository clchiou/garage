from foreman import define_parameter

from templates import pods


(define_parameter('image-version')
 .with_doc('HAProxy image version.')
 .with_default('1.8.9'))


@pods.app_specifier
def haproxy_app(_):
    return pods.App(
        name='haproxy',
        exec=[
            '/usr/local/sbin/haproxy',
            '-f', '/etc/haproxy/haproxy.cfg',
        ],
        volumes=[
            pods.Volume(
                name='etc-hosts-volume',
                path='/etc/hosts',
                host_path='/etc/hosts',
            ),
            pods.Volume(
                name='haproxy-volume',
                path='/etc/haproxy',
                data='haproxy-volume/haproxy-config.tar.gz',
            ),
        ],
        ports=[
            pods.Port(
                name='web',
                protocol='tcp',
                port=8443,
                host_port=443,
            ),
        ],
    )


@pods.image_specifier
def haproxy_image(parameters):
    return pods.Image(
        image_build_uri='docker://haproxy:%s' % parameters['image-version'],
        name='haproxy',
        app=parameters['haproxy_app'],
    )


haproxy_image.specify_image.depend('haproxy_app/specify_app')


haproxy_image.build_image.depend('//host/docker2aci:install')
