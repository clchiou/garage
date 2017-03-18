from templates import py


py.define_pip_package(
    package='Mako',
    version='1.0.6',
    patterns=[
        'mako',
        # Mako's dependency.
        'MarkupSafe*',
        'markupsafe',
    ],
)
