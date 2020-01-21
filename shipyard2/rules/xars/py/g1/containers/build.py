import shipyard2.rules.xars

shipyard2.rules.xars.define_python_zipapp(
    name='ctr',
    python_version='3.7',
    packages=[
        'py/g1/apps',
        'py/g1/bases',
        'py/g1/containers',
        'py/g1/scripts',
        'py/startup',
    ],
)
