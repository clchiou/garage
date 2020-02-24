import shipyard2.rules.pythons

shipyard2.rules.pythons.define_package(
    deps=[
        '//py/g1/asyncs/bases:build',
        '//py/g1/bases:build',
    ],
    extras=[
        (
            'parts',
            [
                '//py/g1/apps:build',
                '//py/g1/asyncs/agents:build/parts',
                '//py/g1/http/servers:build/parts',
            ],
        ),
    ],
)
