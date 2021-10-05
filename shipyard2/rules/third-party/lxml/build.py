import shipyard2.rules.bases
import shipyard2.rules.pythons

shipyard2.rules.bases.define_distro_packages([
    'libxml2-dev',
    'libxslt1-dev',
])

(shipyard2.rules.pythons.define_pypi_package('lxml', '4.6.3').build\
 .depend('install')
 )
