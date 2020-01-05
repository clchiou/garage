import shipyard2.rules.pythons

shipyard2.rules.pythons.define_package(
    deps=[
        '//py/g1/asyncs/bases:build',
        '//py/g1/bases:build',
        '//py/g1/threads:build',
        '//third-party/lxml:build',
        '//third-party/requests:build',
    ],
    extras=[
        ('parts', ['//py/g1/apps:build/asyncs']),
    ],
)
