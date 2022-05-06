import shipyard2.rules.pythons

shipyard2.rules.pythons.define_package(
    build_time_deps=[
        '//python/g1/devtools/buildtools:build',
    ],
    deps=[
        '//python/g1/bases:build',
    ],
    extras=[
        ('yamls', ['//third-party/pyyaml:build']),
    ],
)
