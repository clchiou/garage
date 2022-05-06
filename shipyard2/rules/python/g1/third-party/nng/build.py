import shipyard2.rules.pythons

shipyard2.rules.pythons.define_package(
    deps=[
        '//python/g1/bases:build',
        '//third-party/nng:build',
    ],
    extras=[
        (
            'asyncs',
            [
                '//python/g1/asyncs/bases:build',
                '//python/g1/asyncs/kernels:build',
            ],
        ),
    ],
)
