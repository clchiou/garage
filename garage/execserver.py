"""Execute Python codes from clients."""

# NOTE: This module is Python 2 compatible.

import argparse
import contextlib
import logging
import os
import os.path
import sys
import threading
from argparse import Namespace
from multiprocessing.connection import Listener


LOG = logging.getLogger(__name__)
LOG.addHandler(logging.NullHandler())
LOG_FORMAT = '%(asctime)s %(levelname)s %(name)s %(threadName)s: %(message)s'


def run_server(listener):
    server_vars = Namespace(
        wait=threading.Event(),
        exit=threading.Event(),
        workers=[],
    )
    server_thread = threading.Thread(
        name='server',
        target=server,
        args=(listener, server_vars),
    )
    server_thread.daemon = True
    server_thread.start()
    interruptable_wait(server_vars.exit)
    if server_vars.wait.is_set():
        LOG.info('wait workers')
        for worker_thread in server_vars.workers:
            worker_thread.join()
        # We don't join on the server thread because unfortunately it
        # will most likely be blocked in listener.accept()...
    LOG.info('exit')


def interruptable_wait(event):
    # Unfortunately event.wait() is not interruptable :(
    while not event.is_set():
        event.wait(3600)


def server(listener, server_vars):
    global_vars = {}
    while not server_vars.exit.is_set():
        conn = listener.accept()
        try:
            LOG.info('accept %s', listener.last_accepted)
            worker_vars = Namespace(
                address=listener.last_accepted,
            )
            worker_thread = threading.Thread(
                name='worker-%02d' % (1 + len(server_vars.workers)),
                target=worker,
                args=(
                    maybe_closing(conn),
                    server_vars,
                    worker_vars,
                    global_vars,
                ),
            )
            server_vars.workers.append(worker_thread)
            worker_thread.daemon = True
            worker_thread.start()
            conn = None  # conn is transfered to worker_thread.
        finally:
            if conn is not None:
                conn.close()
    LOG.info('exit')


def worker(conn_manager, server_vars, worker_vars, global_vars):
    with conn_manager as conn:
        _worker(conn, server_vars, worker_vars, global_vars)


SUCCESS = {'success': True}


def _worker(conn, server_vars, worker_vars, global_vars):
    # Say hello to the client!
    conn.send({
        'version_info': tuple(sys.version_info),
    })
    local_vars = {}
    filename = format_address(worker_vars.address)
    while not server_vars.exit.is_set():
        try:
            request = conn.recv()
        except EOFError:
            break
        if 'command' not in request:
            conn.send({
                'success': False,
                'reason': 'need "command"',
            })
            continue
        command = request['command']
        LOG.info('receive command %r', command)
        if command == 'shutdown':
            server_vars.exit.set()
            conn.send(SUCCESS)
            break
        elif command == 'exit':
            conn.send(SUCCESS)
            break
        elif command == 'set-wait':
            if request.get('value', True):
                server_vars.wait.set()
            else:
                server_vars.wait.clear()
            conn.send(SUCCESS)
        elif command == 'execute':
            try:
                _command_execute(
                    request, conn, global_vars, local_vars, filename)
            except Exception as exc:
                conn.send({
                    'success': False,
                    'reason': 'uncaught exception',
                    'exception': str(exc),
                })
                raise
        elif command == 'get':
            try:
                _command_get(request, conn, global_vars, local_vars)
            except Exception as exc:
                conn.send({
                    'success': False,
                    'reason': 'uncaught exception',
                    'exception': str(exc),
                })
                raise
        else:
            LOG.warning('unknown command %r', command)
            conn.send({
                'success': False,
                'reason': 'unknown command',
                'command': command,
            })
    LOG.info('exit')


def _command_execute(request, conn, global_vars, local_vars, filename):
    if 'source' not in request:
        conn.send({
            'success': False,
            'reason': 'need "source" argument',
        })
        return
    source = request['source']
    filename = request.get('filename', filename)
    try:
        code = compile(source, filename, 'exec')
    except SyntaxError as exc:
        LOG.exception('cannot compile for %s', filename)
        conn.send({
            'success': False,
            'reason': 'cannot compile',
            'filename': filename,
            'exception': str(exc),
        })
        return
    exec(code, global_vars, local_vars)
    conn.send(SUCCESS)


def _command_get(request, conn, global_vars, local_vars):
    if 'variable' not in request:
        conn.send({
            'success': False,
            'reason': 'need "variable" argument',
        })
        return
    variable = request['variable']
    if variable not in local_vars and variable not in global_vars:
        conn.send({
            'success': False,
            'reason': 'undefined variable',
            'variable': variable,
        })
        return
    value = local_vars.get(variable) or global_vars.get(variable)
    conn.send({'success': True, 'variable': variable, 'value': value})


def format_address(address):
    if isinstance(address, tuple):
        return '%s:%s' % (address)
    else:
        return str(address)


def main(argv):
    parser = argparse.ArgumentParser(description="""
    Execute Python codes from clients.
    """)
    parser.add_argument(
        '-v', '--verbose', action='count', default=0,
        help='verbose output')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--server-address', metavar=('ADDRESS', 'PORT'), nargs=2,
        help="""set AF_INET -style address of server""")
    group.add_argument(
        '--server-path', metavar='PATH',
        help="""set AF_UNIX or AF_PIPE -style path that server listens on""")
    parser.add_argument(
        '--authkey-var', metavar='VAR', default='AUTHKEY',
        help="""read authkey from this environment variable
                (default %(default)s""")
    args = parser.parse_args(argv[1:])

    if args.verbose == 0:
        level = logging.WARNING
    else:
        level = logging.INFO
    logging.basicConfig(level=level, format=LOG_FORMAT)

    if args.server_address:
        address = (args.server_address[0], int(args.server_address[1]))
    else:
        address = args.server_path

    authkey = os.getenv(args.authkey_var)
    if authkey is None:
        parser.error('cannot read authkey from %s' % args.authkey_var)
        return 2
    if sys.version_info.major > 2:
        authkey = bytes(authkey, encoding='ascii')

    threading.current_thread().name = 'main'
    with maybe_closing(Listener(address, authkey=authkey)) as listener:
        run_server(listener)

    return 0


def maybe_closing(context_manager):
    for attr in ('__enter__', '__exit__'):
        if not hasattr(context_manager, attr):
            return contextlib.closing(context_manager)
    return context_manager


if __name__ == '__main__':
    sys.exit(main(sys.argv))
