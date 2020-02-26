import shipyard2.rules.pythons

shipyard2.rules.pythons.define_package(
    deps=[],
    extras=[
        (
            'executors',
            [
                '//py/g1/threads:build/parts',
            ],
        ),
        (
            'tasks',
            [
                '//py/g1/asyncs/agents:build/parts',
                '//py/g1/asyncs/bases:build',
                '//py/g1/bases:build',
                '//py/startup:build',
            ],
        ),
    ],
)
