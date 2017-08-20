from templates import common, py


common.define_distro_packages(['gcc', 'libjpeg-turbo8-dev', 'pkg-config'])


rules = py.define_package(package='imagetools')
rules.build.depend('//host/buildtools:install')
rules.build.depend('install_packages')
