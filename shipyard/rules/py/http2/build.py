from templates import py


rules = py.define_package(package='http2')
rules.build.depend('//cc/nghttp2:build')
rules.build.depend('//py/curio:build')
rules.build.depend('//py/garage:build')
rules.tapeout.depend('//cc/nghttp2:tapeout')
rules.tapeout.depend('//py/curio:tapeout')
rules.tapeout.depend('//py/garage:tapeout')
