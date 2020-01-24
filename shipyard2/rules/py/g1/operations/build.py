import shipyard2.rules.pythons

shipyard2.rules.pythons.define_package(
    build_time_deps=[
        '//py/g1/devtools/buildtools:build',
    ],
    deps=[
        '//py/g1/bases:build',
        '//py/g1/containers:build',
    ],
    extras=[
        (
            'apps',
            [
                '//py/g1/apps:build',
                '//py/g1/containers:build/scripts',
                '//py/g1/scripts:build/parts',
                '//py/g1/texts:build',
            ],
        ),
    ],
)
