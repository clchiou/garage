import shipyard2.rules.pythons

shipyard2.rules.pythons.define_package(
    deps=[
        '//python/g1/asyncs/bases:build',
        '//python/g1/bases:build',
        '//third-party/nghttp2:build',
    ],
    extras=[
        (
            'parts',
            [
                '//python/g1/apps:build',
                '//python/g1/networks/servers:build/parts',
            ],
        ),
    ],
)
