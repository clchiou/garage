"""Host-only environment for Node.js."""

from pathlib import Path

from foreman import define_parameter, decorate_rule
from shipyard import (
    ensure_file,
    execute,
    install_packages,
)


(define_parameter('npm_prefix')
 .with_doc("""Location host-only npm.""")
 .with_type(Path)
 .with_derive(lambda ps: ps['//base:build'] / 'host/npm-host')
)


@decorate_rule('//base:build')
def install(parameters):
    """Set up host-only environment for Node.js."""
    if not Path('/usr/bin/node').exists():
        install_packages(['nodejs', 'npm'])
        contents = 'prefix = %s\n' % parameters['npm_prefix'].absolute()
        (Path.home() / '.npmrc').write_text(contents)
        # Ubuntu systems use `nodejs` rather than `node` :(
        if not Path('/usr/bin/node').exists():
            ensure_file('/usr/bin/nodejs')
            execute('sudo ln --symbolic nodejs node'.split(), cwd='/usr/bin')
