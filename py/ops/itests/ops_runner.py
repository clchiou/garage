import json
import unittest.mock
import sys
from pathlib import Path

from ops.onboard import run_main


state_path = Path('/tmp/ops_runner_state.json')


if state_path.exists():
    state = json.loads(state_path.read_text())
    systemd_enabled = set(state['systemd_enabled'])
    systemd_started = set(state['systemd_started'])
else:
    systemd_enabled = set()
    systemd_started = set()


for target, mock in [
        ('systemctl_daemon_reload', lambda: None),
        ('systemctl_is_enabled', systemd_enabled.__contains__),
        ('systemctl_is_active', systemd_started.__contains__),
        ('systemctl_enable', systemd_enabled.add),
        ('systemctl_disable', systemd_enabled.discard),
        ('systemctl_start', systemd_started.add),
        ('systemctl_stop', systemd_started.discard),
]:
    unittest.mock.patch('garage.scripts.' + target, mock).__enter__()


try:
    run_main()
finally:
    state_path.write_text(json.dumps({
        'systemd_enabled': list(systemd_enabled),
        'systemd_started': list(systemd_started),
    }))
    print(
        'ops_runner_state.json: \n%s' % state_path.read_text(),
        file=sys.stderr,
    )
