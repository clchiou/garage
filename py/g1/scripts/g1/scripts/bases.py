"""Helpers for constructing ``subprocess.run`` calls contextually.

NOTE: For the ease of use, this module implements context with global
variables, and thus is not concurrent safe (not thread safe and not
asynchronous coroutine safe).  Although we could redesign the interface
to make it concurrent safe (like requiring passing around context
explicitly or using stdlib's contextvars), for now we think ease of use
is more important then concurrent safe (we might change our mind later).
"""

__all__ = [
    'popen',
    'run',
    # Context manipulations.
    'doing_capture_output',
    'doing_check',
    'doing_dry_run',
    'get_cwd',
    'get_dry_run',
    'preserving_sudo_envs',
    'using_cwd',
    'using_input',
    'using_relative_cwd',
    'using_prefix',
    'using_stderr',
    'using_stdin',
    'using_stdout',
    'using_sudo',
]

import contextlib
import logging
import subprocess
from pathlib import Path

from g1.bases.assertions import ASSERT

LOG = logging.getLogger(__name__)

# We don't use threading.local here since we don't pretend this module
# is thread safe.
_CONTEXT = {}

# Context entry names and default values.
_CAPTURE_OUTPUT = 'capture_output'
_CHECK = 'check'
_CWD = 'cwd'
_DRY_RUN = 'dry_run'
_INPUT = 'input'
_PREFIX = 'prefix'
_STDIN = 'stdin'
_STDOUT = 'stdout'
_STDERR = 'stderr'
_SUDO = 'sudo'
_SUDO_ENVS = 'sudo_envs'
_DEFAULTS = {
    _CAPTURE_OUTPUT: False,
    _CHECK: True,
    _CWD: None,
    _DRY_RUN: False,
    _INPUT: None,
    _PREFIX: (),
    _STDIN: None,
    _STDOUT: None,
    _STDERR: None,
    _SUDO: False,
    _SUDO_ENVS: (),
}


def _get(name):
    return _get2(name)[0]


def _get2(name):
    """Return (value, is_default) pair."""
    try:
        return _CONTEXT[name], False
    except KeyError:
        return ASSERT.getitem(_DEFAULTS, name), True


@contextlib.contextmanager
def _using(name, new_value):
    """Context of using an entry value."""
    old_value, is_default = _get2(name)
    _CONTEXT[name] = new_value
    try:
        yield old_value
    finally:
        if is_default:
            _CONTEXT.pop(name)
        else:
            _CONTEXT[name] = old_value


def doing_capture_output(capture_output=True):
    return _using(_CAPTURE_OUTPUT, capture_output)


def doing_check(check=True):
    return _using(_CHECK, check)


def get_dry_run():
    return _get(_DRY_RUN)


def doing_dry_run(dry_run=True):
    return _using(_DRY_RUN, dry_run)


def get_cwd():
    cwd = _get(_CWD)
    if cwd is None:
        cwd = Path.cwd()
    if not isinstance(cwd, Path):
        cwd = Path(cwd)
    return cwd


def using_cwd(cwd):
    """Context of using an absolute cwd value."""
    return _using(_CWD, cwd)


def using_relative_cwd(relative_cwd):
    """Context of using a relative cwd value."""
    if relative_cwd is None:
        return _using(_CWD, None)
    else:
        return _using(_CWD, get_cwd() / relative_cwd)


def using_input(input):  # pylint: disable=redefined-builtin
    return _using(_INPUT, input)


def using_stdin(stdin):
    return _using(_STDIN, stdin)


def using_stdout(stdout):
    return _using(_STDOUT, stdout)


def using_stderr(stderr):
    return _using(_STDERR, stderr)


def using_prefix(prefix):
    return _using(_PREFIX, prefix)


def using_sudo(sudo=True):
    return _using(_SUDO, sudo)


def preserving_sudo_envs(sudo_envs):
    return _using(_SUDO_ENVS, sudo_envs)


def popen(args):
    LOG.debug('popen: args=%s, context=%s', args, _CONTEXT)
    # It does not seem like we can return a fake Popen object.
    ASSERT.false(_get(_DRY_RUN))
    return subprocess.Popen(_prepare_args(args), **_prepare_kwargs())


def run(args):
    LOG.debug('run: args=%s, context=%s', args, _CONTEXT)
    if _get(_DRY_RUN):
        # It seems better to return a fake value than None.
        return subprocess.CompletedProcess(args, 0, b'', b'')
    return subprocess.run(
        _prepare_args(args),
        capture_output=_get(_CAPTURE_OUTPUT),
        check=_get(_CHECK),
        input=_get(_INPUT),
        **_prepare_kwargs(),
    )


def _prepare_args(args):
    args = list(map(str, args))
    if _get(_SUDO):
        sudo_envs = _get(_SUDO_ENVS)
        if sudo_envs:
            preserve_envs_arg = ('--preserve-env=%s' % ','.join(sudo_envs), )
        else:
            preserve_envs_arg = ()
        args[:0] = ['sudo', '--non-interactive', *preserve_envs_arg]
    prefix = _get(_PREFIX)
    if prefix:
        args[:0] = prefix
    return args


def _prepare_kwargs():
    kwargs = {
        'cwd': _get(_CWD),
    }
    # Work around subprocess.run limitation that it checks presence of
    # stdin, stdout, and stderr in kwargs, not whether their value is
    # not None.
    for key in (_STDIN, _STDOUT, _STDERR):
        value = _get(key)
        if value is not None:
            kwargs[key] = value
    return kwargs
