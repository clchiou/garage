import shipyard2.rules.pythons

shipyard2.rules.pythons.define_package(
    deps=[
        '//python/g1/asyncs/bases:build',
        '//python/g1/bases:build',
        '//python/g1/threads:build',
        '//third-party/lxml:build',
        '//third-party/requests:build',
    ],
    extras=[
        ('parts', ['//python/g1/apps:build/asyncs']),
    ],
)
