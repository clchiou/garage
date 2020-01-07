import shipyard2.rules.pods

shipyard2.rules.pods.define_pod(
    name='web-server',
    apps=[
        shipyard2.rules.pods.App(
            name='web-server',
            exec=[
                'python3',
                *('-m', 'http.server'),
                *('--directory', '/srv/web'),
                '8000',
            ],
        ),
    ],
    images=['//examples:web-server'],
)
