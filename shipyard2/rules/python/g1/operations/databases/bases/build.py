import shipyard2.rules.capnps
import shipyard2.rules.pythons

shipyard2.rules.pythons.define_package(
    build_time_deps=[
        '//python/g1/devtools/buildtools:build',
        '//third-party/capnproto-java:build',
    ],
    deps=[
        '//python/g1/bases:build',
        '//python/g1/messaging:build',
        # Sadly it has to depend on capnp even when no-extra is required
        # because `setup.py install` always runs compile_schemas
        # regardless of extra or not.
        '//python/g1/third-party/capnp:build',
    ],
    extras=[
        (
            'capnps',
            [
                '//python/g1/messaging:build/wiredata.capnps',
                '//python/g1/third-party/capnp:build',
            ],
        ),
    ],
    make_global_options=shipyard2.rules.capnps.make_global_options,
)
