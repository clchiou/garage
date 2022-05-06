import shipyard2.rules.xars

shipyard2.rules.xars.define_zipapp(
    name='ctr',
    # Ubuntu 20.04 LTS has Python 3.8.
    python_version='3.8',
    packages=[
        'python/g1/apps',
        'python/g1/bases',
        'python/g1/containers',
        'python/g1/files',
        'python/g1/scripts',
        'python/g1/texts',
        'python/startup',
    ],
)
