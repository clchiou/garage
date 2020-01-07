import foreman

from g1 import scripts

import shipyard2.rules.images

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
