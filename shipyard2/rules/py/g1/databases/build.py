import shipyard2.rules.pythons

shipyard2.rules.pythons.define_package(
    deps=[
        '//py/g1/bases:build',
        '//third-party/sqlalchemy:build',
    ],
    extras=[
        ('parts', ['//py/g1/apps:build']),
    ],
)
