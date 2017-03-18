from templates import py


rules = py.define_package(package='nanomsg')
rules.build.depend('//cc/nanomsg:build')
rules.build.depend('//py/curio:build')
rules.tapeout.depend('//cc/nanomsg:tapeout')
rules.tapeout.depend('//py/curio:tapeout')
