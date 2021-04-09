"""Build third-party pods.

We assume the following HAProxy pod directory layout.

Files created by ops tool:
* haproxy.cfg is the configuration file.
* site.pem is the PEM file of certificate bundle.
* user-agent-blacklist.txt lists the user agents to be blocked.

Files created by HAProxy:
* admin.sock is the admin stats unix domain socket.
* haproxy-master.sock is the unix domain socket master CLI.
* haproxy.pid is the PID file.
* server-state is the file of saved HAProxy server state.
"""

from pathlib import Path

import shipyard2.rules.pods

HAPROXY_PATH = Path('/srv/third-party/haproxy/v1')

HAPROXY_SERVICE_SECTION = '''\
Environment="CONFIG={haproxy_path}/haproxy.cfg"
Environment="PIDFILE={haproxy_path}/haproxy.pid"
Environment="EXTRAOPTS=-S {haproxy_path}/haproxy-master.sock"
Environment="STATS_PORT={{stats_port}}"
ExecStartPre=/usr/sbin/haproxy -f $CONFIG -c -q $EXTRAOPTS
ExecStart=/usr/sbin/haproxy -Ws -f $CONFIG -p $PIDFILE $EXTRAOPTS
ExecReload=/usr/sbin/haproxy -f $CONFIG -c -q $EXTRAOPTS
ExecReload=/bin/kill -USR2 $MAINPID
ExecStopPost=/usr/sbin/pod-exit "%n"
KillMode=mixed
Restart=no
SuccessExitStatus=143
Type=notify
LimitNOFILE=65536'''.format(haproxy_path=HAPROXY_PATH)

shipyard2.rules.pods.define_pod(
    name='haproxy',
    apps=[
        shipyard2.rules.pods.App(
            name='haproxy',
            service_section=HAPROXY_SERVICE_SECTION,
        ),
    ],
    images=[
        '//third-party:haproxy',
    ],
    mounts=[
        shipyard2.rules.pods.Mount(
            source=str(HAPROXY_PATH),
            target=str(HAPROXY_PATH),
            read_only=False,
        ),
    ],
    systemd_unit_groups=[
        shipyard2.rules.pods.SystemdUnitGroup(
            units=[
                shipyard2.rules.pods.SystemdUnitGroup.Unit(
                    name='haproxy.service',
                    content=shipyard2.rules.pods.make_pod_service_content(
                        description='HAProxy Server',
                    ),
                ),
            ],
        ),
    ],
    token_names={
        'stats_port': 'ops_free_port',
    },
)
