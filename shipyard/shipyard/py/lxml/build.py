"""Install lxml."""

from shipyard import py


py.define_pip_package(
    package_name='lxml',
    version='3.6.0',
    dep_pkgs=[
        'libxml2-dev',
        'libxslt1-dev',
    ],
    dep_libs=[
        'libexslt.so',
        'libicudata.so',
        'libicuuc.so',
        'libstdc++.so',
        'libxml2.so',
        'libxslt.so',
    ],
)
