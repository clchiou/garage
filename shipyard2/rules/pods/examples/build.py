import shipyard2.rules.pods

UNIT_CONTENTS = '''\
[Unit]
Description=example web server

[Service]
ExecStart=/usr/local/bin/ctr pods run-prepared ${pod_id}

[Install]
WantedBy=multi-user.target
'''

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
    systemd_units=[
        shipyard2.rules.pods.SystemdUnit(
            name='web-server.service',
            contents=UNIT_CONTENTS,
        ),
    ],
)
