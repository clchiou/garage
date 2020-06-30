import shipyard2.rules.xars

shipyard2.rules.xars.define_zipapp(
    name='ctr',
    # Ubuntu 20.04 LTS has Python 3.8.
    python_version='3.8',
    packages=[
        'py/g1/apps',
        'py/g1/bases',
        'py/g1/containers',
        'py/g1/files',
        'py/g1/scripts',
        'py/g1/texts',
        'py/startup',
    ],
)
