import shipyard2.rules.pythons

shipyard2.rules.pythons.define_package(
    deps=[
        '//py/g1/bases:build',
    ],
    extras=[
        ('parts', ['//py/g1/apps:build']),
    ],
)
