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
    LOG.info('server start')
    global_vars = {}
    while not server_vars.exit.is_set():
        conn = listener.accept()
        try:
            LOG.info('accept %r', listener.last_accepted)
            worker = Worker(
                maybe_closing(conn),
                server_vars,
                global_vars,
                listener.last_accepted,
            )
            worker_thread = threading.Thread(
                name='worker-%02d' % (1 + len(server_vars.workers)),
                target=worker.run,
            )
            server_vars.workers.append(worker_thread)
            worker_thread.daemon = True
            worker_thread.start()
            conn = None  # conn is transfered to worker_thread.
        finally:
            if conn is not None:
                conn.close()
    LOG.info('exit')


class Worker(object):

    SUCCESS = {'success': True}

    def __init__(self, conn_manager, server_vars, global_vars, address):
        self.conn_manager = conn_manager
        self.server_vars = server_vars
        self.global_vars = global_vars
        self.exit = False
        if isinstance(address, tuple):
            self.filename = '%s:%s' % (address)
        else:
            self.filename = str(address)

    def run(self):
        LOG.info('worker start')
        with self.conn_manager as conn:
            conn.send({
                'version_info': tuple(sys.version_info),
            })
            while not self.server_vars.exit.is_set() and not self.exit:
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
                handler = {
                    'shutdown': self.do_shutdown,
                    'exit': self.do_exit,
                    'set-wait': self.do_set_wait,
                    'get': self.do_get,
                    'set': self.do_set,
                    'execute': self.do_execute,
                }.get(command)
                if handler is None:
                    LOG.warning('unknown command %r', command)
                    conn.send({
                        'success': False,
                        'reason': 'unknown command',
                        'command': command,
                    })
                else:
                    try:
                        handler(conn, request)
                    except Exception as exc:
                        conn.send({
                            'success': False,
                            'reason': 'uncaught exception',
                            'exception': str(exc),
                        })
                        raise
        LOG.info('exit')

    def do_shutdown(self, conn, _):
        self.server_vars.exit.set()
        conn.send(Worker.SUCCESS)

    def do_exit(self, conn, _):
        self.exit = True
        conn.send(Worker.SUCCESS)

    def do_set_wait(self, conn, request):
        if request.get('value', True):
            self.server_vars.wait.set()
        else:
            self.server_vars.wait.clear()
        conn.send(Worker.SUCCESS)

    def do_get(self, conn, request):
        if 'name' not in request:
            conn.send({
                'success': False,
                'reason': 'need "name" argument',
            })
            return
        name = request['name']
        if name not in self.global_vars:
            conn.send({
                'success': False,
                'reason': 'undefined variable',
                'name': name,
            })
            return
        conn.send({
            'success': True,
            'name': name,
            'value': self.global_vars[name],
        })

    def do_set(self, conn, request):
        if 'name' not in request:
            conn.send({
                'success': False,
                'reason': 'need "name" argument',
            })
            return
        if 'value' not in request:
            conn.send({
                'success': False,
                'reason': 'need "value" argument',
            })
            return
        self.global_vars[request['name']] = request['value']
        conn.send(Worker.SUCCESS)

    def do_execute(self, conn, request):
        if 'source' not in request:
            conn.send({
                'success': False,
                'reason': 'need "source" argument',
            })
            return
        source = request['source']
        filename = request.get('filename', self.filename)
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
        exec(code, self.global_vars)
        conn.send(Worker.SUCCESS)


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
