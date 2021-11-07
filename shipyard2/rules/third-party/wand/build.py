import shipyard2.rules.bases
import shipyard2.rules.pythons

# Wand does not need the "-dev" package, but we depend on it anyway
# because it is a dummy package that automatically pulls in the current
# libmagickwand package (and so we do not have to hard-code something
# like libmagickwand-6.q16-6 here).
shipyard2.rules.bases.define_distro_packages([
    'libmagickwand-dev',
])

(shipyard2.rules.pythons.define_pypi_package('Wand', '0.6.7').build\
 .depend('install')
 )
