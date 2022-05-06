import shipyard2.rules.pythons

shipyard2.rules.pythons.define_package(
    deps=[
        '//python/g1/messaging:build/pubsub',
        '//python/g1/operations/databases/bases:build/capnps',
    ],
    extras=[
        (
            'parts',
            [
                '//python/g1/apps:build',
                '//python/g1/asyncs/agents:build/parts',
                '//python/g1/asyncs/bases:build',
                '//python/g1/bases:build',
                '//python/g1/messaging:build/parts/pubsub',
            ],
        ),
    ],
)
