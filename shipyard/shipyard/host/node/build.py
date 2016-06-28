"""Host-only environment for Node.js."""

from pathlib import Path

from foreman import define_parameter, decorate_rule
from shipyard import install_packages


(define_parameter('npm_prefix')
 .with_doc("""Location host-only npm.""")
 .with_type(Path)
 .with_derive(lambda ps: ps['//base:build'] / 'host/npm-host')
)


@decorate_rule('//base:build')
def install(parameters):
    """Set up host-only environment for Node.js."""
    if not Path('/usr/bin/nodejs').exists():
        install_packages(['nodejs', 'npm'])
        (Path.home() / '.npmrc').write_text(
            'prefix = %s' % parameters['npm_prefix'].absolute())
