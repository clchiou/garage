from pathlib import Path

import shipyard2.rules.pods

OPS_DB_HOST_PATH = Path('/srv/operations/database/v1')
OPS_DB_PATH = Path('/srv/operations/database')

shipyard2.rules.pods.define_pod(
    name='ops-db',
    apps=[
        shipyard2.rules.pods.App(
            name='ops-db',
            exec=[
                'python3',
                *('-m', 'g1.operations.databases.servers'),
                *(
                    '--parameter',
                    'g1.operations.databases.servers:database.db_url',
                    'sqlite:///%s' % (OPS_DB_PATH / 'ops.db'),
                ),
            ],
        ),
    ],
    images=[
        '//py/g1/operations/databases:ops-db',
    ],
    mounts=[
        shipyard2.rules.pods.Mount(
            source=str(OPS_DB_HOST_PATH),
            target=str(OPS_DB_PATH),
            read_only=False,
        ),
    ],
    # TODO: Add systemd unit files.
    systemd_units=[],
)
