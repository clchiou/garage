from templates import py


py.define_pip_package(
    package='Mako',
    version='1.0.7',
    patterns=[
        'mako',
        # And its dependencies.
        'markupsafe',
    ],
)
