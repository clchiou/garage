from pathlib import Path

from foreman import define_parameter, get_relpath, rule

from garage import scripts

from templates import common


(define_parameter
 .path_typed('npm_prefix')
 .with_doc("""Path to host-only npm packages.""")
 .with_derive(lambda ps: ps['//base:drydock'] / get_relpath() / 'modules'))


common.define_distro_packages(['nodejs', 'npm'])


@rule
@rule.depend('//base:build')
@rule.depend('install_packages')
def install(parameters):
    npmrc = Path.home() / '.npmrc'
    if not npmrc.exists():
        scripts.ensure_contents(
            npmrc, 'prefix = %s\n' % parameters['npm_prefix'])
    # Ubuntu chooses `nodejs` not `node` to avoid conflict
    if not Path('/usr/bin/node').exists():
        scripts.ensure_file('/usr/bin/nodejs')
        with scripts.using_sudo(), scripts.directory('/usr/bin'):
            scripts.execute(['ln', '--symbolic', 'nodejs', 'node'])
