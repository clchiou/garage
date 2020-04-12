import shipyard2.rules.pythons

shipyard2.rules.pythons.define_package(
    deps=[
        '//py/g1/messaging:build/pubsub',
        '//py/g1/operations/databases/bases:build/capnps',
    ],
    extras=[
        (
            'parts',
            [
                '//py/g1/apps:build',
                '//py/g1/asyncs/bases:build',
                '//py/g1/bases:build',
                '//py/g1/messaging:build/parts/pubsub',
            ],
        ),
    ],
)
