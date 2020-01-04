import shipyard2.rules.pythons

(shipyard2.rules.pythons.define_package().build\
 .depend('//py/g1/apps:build')
 .depend('//py/g1/asyncs/bases:build')
 .depend('//py/g1/bases:build')
 .depend('//py/g1/threads:build')
 .depend('//third-party/lxml:build')
 .depend('//third-party/requests:build')
 )
