from pathlib import Path

import shipyard2.rules.pods

OPS_DB_PATH = Path('/srv/operations/database/v1')

shipyard2.rules.pods.define_pod(
    name='database',
    apps=[
        shipyard2.rules.pods.App(
            name='database',
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
        '//operations:database',
    ],
    mounts=[
        shipyard2.rules.pods.Mount(
            source=str(OPS_DB_PATH),
            target=str(OPS_DB_PATH),
            read_only=False,
        ),
    ],
    systemd_unit_groups=[
        shipyard2.rules.pods.SystemdUnitGroup(
            units=[
                shipyard2.rules.pods.SystemdUnitGroup.Unit(
                    name='database.service',
                    content=shipyard2.rules.pods.make_pod_service_content(
                        description='Operations Database Server',
                    ),
                ),
            ],
        ),
    ],
)
