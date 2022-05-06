import shipyard2.rules.pythons

shipyard2.rules.pythons.define_package(
    deps=[
        '//python/g1/bases:build',
        '//third-party/boost:build',
        '//third-party/capnproto:build',
    ],
)
