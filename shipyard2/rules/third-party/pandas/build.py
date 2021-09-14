import shipyard2.rules.pythons

(shipyard2.rules.pythons.define_pypi_package('pandas', '1.3.3')\
 .build.depend('//third-party/numpy:build'))
