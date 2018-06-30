from templates import common, py


# We do not really need to depend on the "-dev" package since Wand
# employs ctypes to wrap libmagickwand, but we depend it anyway for
# convenience.
common.define_distro_packages(['libmagickwand-dev'])


rules = py.define_pip_package(
    package='Wand',
    version='0.4.4',
    patterns=[
        'wand',
    ],
)
rules.build.depend('install_packages')
