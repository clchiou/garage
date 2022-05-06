import shipyard2.rules.pythons

shipyard2.rules.pythons.define_package(
    build_time_deps=[
        '//python/g1/devtools/buildtools:build',
    ],
    deps=[
        '//python/g1/bases:build',
        '//python/startup:build',
    ],
    extras=[
        ('asyncs', ['//python/g1/asyncs/kernels:build']),
        ('yamls', ['//third-party/pyyaml:build']),
    ],
)
