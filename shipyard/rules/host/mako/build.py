"""Install Mako in host-only venv."""

from foreman import rule

from garage import scripts


@rule
@rule.depend('//host/cpython:install')
def install(parameters):
    scripts.execute([parameters['//host/cpython:pip'], 'install', 'Mako'])
