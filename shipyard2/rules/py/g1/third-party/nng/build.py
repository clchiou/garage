import shipyard2.rules.pythons

(shipyard2.rules.pythons.define_package().build\
 .depend('//py/g1/asyncs/bases:build')
 .depend('//py/g1/asyncs/kernels:build')
 .depend('//py/g1/bases:build')
 .depend('//third-party/nng:build')
 )
