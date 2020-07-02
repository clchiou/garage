import shipyard2.rules.xars

shipyard2.rules.xars.define_xar(
    name='reqrep-client',
    exec_relpath='usr/local/bin/run-reqrep-client',
    image='//examples:reqrep-client',
)
