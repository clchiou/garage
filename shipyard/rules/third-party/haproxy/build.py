from foreman import define_parameter

from templates import pods


(define_parameter('image-version')
 .with_doc('HAProxy image version.')
 .with_default('1.8.9'))


(define_parameter('image-checksum')
 .with_doc('HAProxy image checksum.')
 .with_default('sha512-ce1abc1223fbcdc670cd5dfd83f10c8f018e178ea93b76e671dc19b5c4dc169b'))


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
        id=parameters['image-checksum'],
        image_uri='docker://haproxy:%s' % parameters['image-version'],
        name='haproxy',
        app=parameters['haproxy_app'],
    )


haproxy_image.specify_image.depend('haproxy_app/specify_app')
