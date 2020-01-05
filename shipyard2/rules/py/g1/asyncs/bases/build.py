import shipyard2.rules.pythons

shipyard2.rules.pythons.define_package(
    deps=[
        '//py/g1/asyncs/kernels:build',
        '//py/g1/bases:build',
    ],
)
