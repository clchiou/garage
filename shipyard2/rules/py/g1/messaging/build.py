import shipyard2.rules.pythons

shipyard2.rules.pythons.define_package(
    deps=[
        '//py/g1/bases:build',
    ],
    extras=[
        (
            'parts',
            [
                '//py/g1/apps:build',
                '//py/g1/asyncs/servers:build/parts',
            ],
        ),
        (
            'reqrep',
            [
                '//py/g1/asyncs/bases:build',
                '//py/g1/third-party/nng:build/asyncs',
            ],
        ),
        ('wiredata.capnps', ['//py/g1/third-party/capnp:build']),
    ],
)
