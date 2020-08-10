from pathlib import Path

import foreman

from g1 import scripts

import shipyard2.rules.images

HAPROXY_PATH = Path('/srv/third-party/haproxy/v1')

shipyard2.rules.images.define_image(
    name='haproxy',
    rules=[
        '//third-party/haproxy:build',
        'haproxy/setup',
    ],
    filters=[
        ('include', '/usr/sbin/'),
        ('include', '/usr/sbin/haproxy'),
        ('exclude', '/usr/sbin/**'),
        ('include', '/usr/share/'),
        ('include', '/usr/share/ca-certificates/'),
        ('include', '/usr/share/ca-certificates/**'),
        # Include /var/lib/haproxy for the HAProxy jail.
        ('include', '/var/'),
        ('include', '/var/lib/'),
        ('include', '/var/lib/haproxy/'),
    ],
)


@foreman.rule('haproxy/setup')
@foreman.rule.depend('//bases:build')
def haproxy_setup(parameters):
    del parameters  # Unused.
    with scripts.using_sudo():
        scripts.mkdir(HAPROXY_PATH)
