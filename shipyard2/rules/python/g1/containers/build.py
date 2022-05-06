import shipyard2.rules.pythons

shipyard2.rules.pythons.define_package(
    build_time_deps=[
        '//python/g1/devtools/buildtools:build',
    ],
    deps=[
        '//python/g1/bases:build',
    ],
    extras=[
        (
            'apps',
            [
                '//python/g1/apps:build',
                '//python/g1/files:build',
                '//python/g1/scripts:build/parts',
                '//python/g1/texts:build',
            ],
        ),
        (
            'scripts',
            [
                '//python/g1/scripts:build',
            ],
        ),
    ],
)
