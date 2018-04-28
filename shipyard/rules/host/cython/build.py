from foreman import rule

from garage import scripts


PACKAGE = 'cython'
VERSION = '0.28.2'


@rule
@rule.depend('//py/cpython:build')
def install(parameters):
    with scripts.using_sudo():
        scripts.execute([
            parameters['//py/cpython:pip'], 'install',
            '%s==%s' % (PACKAGE, VERSION),
        ])
