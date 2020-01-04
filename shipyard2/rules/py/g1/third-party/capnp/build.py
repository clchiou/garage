import shipyard2.rules.pythons

(shipyard2.rules.pythons.define_package().build\
 .depend('//py/g1/bases:build')
 .depend('//third-party/boost:build')
 .depend('//third-party/capnproto:build')
 )
