from templates import py


py.define_pip_package(
    package='lxml',
    version='3.7.3',
    distro_packages=[
        'libxml2-dev',
        'libxslt1-dev',
    ],
)
