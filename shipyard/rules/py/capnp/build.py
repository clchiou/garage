from foreman import define_rule

from templates import py


(define_rule('config')
 .depend('//cc/boost:config', parameters={'//cc/boost:libraries': ['python']})
 .reverse_depend('//cc/boost:build')
)


rules = py.define_package(package='capnp')
rules.build.depend('config')
rules.build.depend('//cc/boost:build')
rules.build.depend('//cc/capnproto:build')
rules.build.depend('//host/buildtools:install')
rules.tapeout.depend('//cc/boost:tapeout')
rules.tapeout.depend('//cc/capnproto:tapeout')
