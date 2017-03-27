from templates import py


rules = py.define_package(package='garage')
rules.build.depend('//host/buildtools:install')
