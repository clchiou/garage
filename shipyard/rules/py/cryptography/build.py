from templates import py


py.define_pip_package(
    package='cryptography',
    version='2.3.1',
    patterns=[
        'cryptography',
        # And its dependencies.
        'asn1crypto',
        'cffi',
        '_cffi_backend*',
        '.libs_cffi_backend*',
        'idna',
        'pycparser',
        'six.py',
    ],
)
