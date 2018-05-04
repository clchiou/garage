from templates import py


py.define_pip_package(
    package='requests',
    version='2.18.4',
    patterns=[
        'requests',
        # And its dependencies.
        'chardet',
        'idna',
        'urllib3',
        'certifi',
    ],
)
