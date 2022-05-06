import foreman

from g1 import scripts

import shipyard2.rules.images

shipyard2.rules.images.define_image(
    name='empty',
    rules=[
        '//bases:build',
    ],
)

shipyard2.rules.images.define_xar_image(
    name='reqrep-client',
    rules=[
        '//python/g1/messaging:reqrep-client/build',
        'reqrep-client/setup',
    ],
)


@foreman.rule('reqrep-client/setup')
@foreman.rule.depend('//bases:build')
def reqrep_client_setup(parameters):
    del parameters  # Unused.
    shipyard2.rules.images.generate_exec_wrapper(
        'usr/local/bin/reqrep-client',
        'usr/local/bin/run-reqrep-client',
    )


shipyard2.rules.images.define_image(
    name='web-server',
    rules=[
        '//third-party/cpython:build',
        'web-server/setup',
    ],
)


@foreman.rule('web-server/setup')
@foreman.rule.depend('//bases:build')
def web_server_setup(parameters):
    del parameters  # Unused.
    with scripts.using_sudo():
        scripts.mkdir('/srv/web')
        scripts.cp(foreman.to_path('web-server/index.html'), '/srv/web')
