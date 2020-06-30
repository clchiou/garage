import shipyard2.rules.xars

shipyard2.rules.xars.define_zipapp(
    name='ops',
    python_version='3.7',
    packages=[
        'py/g1/apps',
        'py/g1/bases',
        'py/g1/containers',
        'py/g1/files',
        'py/g1/operations/cores',
        'py/g1/scripts',
        'py/g1/texts',
        'py/startup',
    ],
)
