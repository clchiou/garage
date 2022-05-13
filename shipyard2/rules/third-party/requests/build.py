import shipyard2.rules.pythons

shipyard2.rules.pythons.define_pypi_package(
    'requests',
    '2.26.0',
    extras=['socks'],
)
