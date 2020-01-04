import shipyard2.rules.pythons

(shipyard2.rules.pythons.define_package().build\
 .depend('//py/g1/asyncs/bases:build')
 .depend('//py/g1/bases:build')
 .depend('//py/g1/third-party/capnp:build')
 .depend('//py/g1/third-party/nng:build')
 )
