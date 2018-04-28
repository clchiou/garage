from templates import common, py


common.define_distro_packages(['libxml2-dev', 'libxslt1-dev'])


rules = py.define_pip_package(
    package='lxml',
    version='4.2.1',
)
rules.build.depend('install_packages')
