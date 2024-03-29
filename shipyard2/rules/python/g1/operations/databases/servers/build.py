import shipyard2.rules.pythons

shipyard2.rules.pythons.define_package(
    deps=[
        '//python/g1/asyncs/bases:build',
        '//python/g1/bases:build',
        '//python/g1/databases:build',
        '//python/g1/operations/databases/bases:build',
        '//third-party/sqlalchemy:build',
    ],
    extras=[
        (
            'apps',
            [
                '//python/g1/apps:build/asyncs',
                '//python/g1/asyncs/agents:build/parts',
                '//python/g1/asyncs/kernels:build',
                '//python/g1/operations/databases/servers:build/parts',
            ],
        ),
        (
            'parts',
            [
                '//python/g1/apps:build/asyncs',
                '//python/g1/asyncs/agents:build/parts',
                '//python/g1/asyncs/bases:build',
                '//python/g1/databases:build/parts',
                '//python/g1/messaging:build/parts/pubsub',
                '//python/g1/messaging:build/parts/servers',
                '//python/g1/messaging:build/pubsub',
                '//python/g1/messaging:build/reqrep',
                '//python/g1/operations/databases/bases:build/capnps',
            ],
        ),
    ],
)
