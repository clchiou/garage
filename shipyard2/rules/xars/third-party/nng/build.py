import shipyard2.rules.xars

shipyard2.rules.xars.define_xar(
    name='nngcat',
    exec_relpath='usr/local/bin/run-nngcat',
    image='//third-party/nng:nngcat',
)
