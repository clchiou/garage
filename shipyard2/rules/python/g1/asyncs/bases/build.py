import shipyard2.rules.pythons

shipyard2.rules.pythons.define_package(
    deps=[
        '//python/g1/asyncs/kernels:build',
        '//python/g1/bases:build',
    ],
)
