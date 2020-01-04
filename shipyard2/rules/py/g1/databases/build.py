import shipyard2.rules.pythons

(shipyard2.rules.pythons.define_package().build\
 .depend('//py/g1/bases:build')
 .depend('//third-party/sqlalchemy:build')
 )
