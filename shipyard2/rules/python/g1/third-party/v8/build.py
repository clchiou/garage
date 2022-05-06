import shipyard2.rules.pythons


def make_global_options(ps):
    v8_path = ps['//bases:drydock'] / 'third-party/v8/v8'
    v8_out_path = v8_path / 'out.gn/x64.release'
    return [
        'copy_files',
        '--src-dir=%s' % v8_out_path,
        'build_ext',
        '--include-dirs=%s:%s' % (v8_path, v8_path / 'include'),
        '--library-dirs=%s' % (v8_out_path / 'obj'),
    ]


shipyard2.rules.pythons.define_package(
    build_time_deps=[
        '//python/g1/devtools/buildtools:build',
    ],
    deps=[
        '//third-party/boost:build',
        '//third-party/v8:build',
    ],
    make_global_options=make_global_options,
)
