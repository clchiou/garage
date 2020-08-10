"""Install HAProxy."""

import foreman

import shipyard2.rules.bases

shipyard2.rules.bases.define_distro_packages([
    'haproxy',
    # For /etc/ssl/certs and /usr/share/ca-certificates.
    'ca-certificates',
    'openssl',
])

# Nothing to do since we use HAProxy from the distro.
foreman.define_rule('build').depend('//bases:build').depend('install')
