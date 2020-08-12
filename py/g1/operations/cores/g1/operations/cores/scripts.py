"""Helpers for scripting ops."""

__all__ = [
    'ops',
    # Alert commands.
    'ops_send_alert',
    # Pod commands.
    'ops_list_pods',
    'ops_list_pod_units',
    'ops_start_pod',
    'ops_restart_pod',
    'ops_stop_pod',
    # Env commands.
    'ops_list_envs',
]

import csv
import io
import logging

from g1 import scripts
from g1.bases.assertions import ASSERT

_VERBOSE = None


def ops(args):
    global _VERBOSE
    if _VERBOSE is None:
        if logging.getLogger().isEnabledFor(logging.DEBUG):
            _VERBOSE = ('--verbose', )
        else:
            _VERBOSE = ()
    return scripts.run(['ops', *_VERBOSE, *args])


def ops_send_alert(level, title, description):
    return ops([
        'alerts',
        'send',
        *('--level', level),
        title,
        description,
    ])


def ops_list_pods():
    with scripts.doing_capture_stdout():
        proc = ops([
            'pods',
            'list',
            *('--format', 'csv'),
            *('--header', 'true'),
            *('--columns', 'label,version,id'),
        ])
        pods = {}
        for row in csv.DictReader(io.StringIO(proc.stdout.decode('utf-8'))):
            pods[row['id']] = row
    return list(pods.values())


def ops_list_pod_units(columns=('label', 'version', 'id', 'name')):
    with scripts.doing_capture_stdout():
        proc = ops([
            'pods',
            'list',
            *('--format', 'csv'),
            *('--header', 'true'),
            *('--columns', ','.join(ASSERT.not_empty(columns))),
        ])
        return list(csv.DictReader(io.StringIO(proc.stdout.decode('utf-8'))))


def ops_start_pod(label, version, *, units=(), unit_all=False):
    return _ops_start_or_stop_pod('start', label, version, units, unit_all)


def ops_restart_pod(label, version, *, units=(), unit_all=False):
    return _ops_start_or_stop_pod('restart', label, version, units, unit_all)


def ops_stop_pod(label, version, *, units=(), unit_all=False):
    return _ops_start_or_stop_pod('stop', label, version, units, unit_all)


def _ops_start_or_stop_pod(cmd, label, version, units, unit_all):
    units_args = []
    for unit in units:
        units_args.append('--unit')
        units_args.append(unit)
    return ops([
        'pods',
        cmd,
        *units_args,
        *(('--unit-all', 'true') if unit_all else ()),
        label,
        version,
    ])


def ops_list_envs():
    with scripts.doing_capture_stdout():
        proc = ops([
            'envs',
            'list',
            *('--format', 'csv'),
            *('--header', 'false'),
            *('--columns', 'name,value'),
        ])
        return {
            row[0]: row[1]
            for row in csv.reader(io.StringIO(proc.stdout.decode('utf-8')))
        }
