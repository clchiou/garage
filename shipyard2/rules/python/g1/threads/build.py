import shipyard2.rules.pythons

shipyard2.rules.pythons.define_package(
    deps=[
        '//python/g1/bases:build',
    ],
    extras=[
        ('parts', ['//python/g1/apps:build']),
    ],
)
