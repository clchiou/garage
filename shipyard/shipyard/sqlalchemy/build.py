"""Install SQLAlchemy."""

from shipyard import py


py.define_pip_package(
    package_name='SQLAlchemy',
    version='1.0.13',
    patterns=['*sqlalchemy*'],
)
