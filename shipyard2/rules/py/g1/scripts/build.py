import shipyard2.rules.pythons

shipyard2.rules.pythons.define_package(
    host_deps=[
        '//py/g1/devtools/buildtools:build',
    ],
    deps=[
        '//py/g1/bases:build',
    ],
    extras=[
        ('parts', ['//py/g1/apps:build']),
    ],
)
