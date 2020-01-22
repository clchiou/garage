import foreman

import shipyard2.rules.images

shipyard2.rules.images.define_image(
    name='nngcat',
    rules=[
        '//third-party/nng:build',
        'nngcat/setup',
    ],
)


@foreman.rule('nngcat/setup')
@foreman.rule.depend('//bases:build')
def nngcat_setup(parameters):
    del parameters  # Unused.
    shipyard2.rules.images.generate_exec_wrapper(
        'usr/local/bin/nngcat',
        'usr/local/bin/run-nngcat',
    )
