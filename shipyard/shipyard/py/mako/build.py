"""Install Mako."""

from shipyard import py

py.define_pip_package(
    package_name='Mako',
    version='1.0.4',
    patterns=[
        'mako*',
        # Mako's dependency.
        'MarkupSafe*',
        'markupsafe*',
    ],
)
