__all__ = [
    'assert_group_exist',
    'assert_root_privilege',
    'has_root_privilege',
]

import grp
import os

from .assertions import ASSERT


def assert_group_exist(name):
    try:
        grp.getgrnam(name)
    except KeyError:
        raise AssertionError('expect group: %s' % name) from None


def assert_root_privilege():
    ASSERT(has_root_privilege(), 'expect root privilege')


def has_root_privilege():
    return os.geteuid() == 0
