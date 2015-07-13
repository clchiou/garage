"""A server that execute arbitrary Python code."""

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
    wait_forever(server_vars.exit)
    if server_vars.wait.is_set():
        LOG.info('wait workers')
        for worker_thread in server_vars.workers:
            worker_thread.join()
        # We don't join on the server thread because unfortunately it
        # will most likely be blocked on listener.accept().
    LOG.info('exit')


def wait_forever(event):
    # Unfortunately event.wait() without timeout is not uninterruptable.
    while not event.is_set():
        event.wait(3600)


def server(listener, server_vars):
    LOG.info('start server')
    global_vars = {}
    while not server_vars.exit.is_set():
        conn = listener.accept()
        try:
            LOG.info('accept %r', listener.last_accepted)
            worker = Worker(
                closing(conn),
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
            conn = None  # conn is transfered to the worker.
        finally:
            # Close conn only when it is not transfered to the worker.
            if conn is not None:
                conn.close()
    LOG.info('exit')


class Worker(object):

    VERSION_INFO = {'version_info': tuple(sys.version_info)}

    OKAY = {}
    ERROR_REQUIRE_COMMAND = {'error': 'require command'}
    ERROR_REQUIRE_NAME = {'error': 'require name argument'}
    ERROR_REQUIRE_VALUE = {'error': 'require value argument'}
    ERROR_REQUIRE_SOURCE = {'error': 'require source argument'}

    def __init__(self, conn_manager, server_vars, global_vars, address):
        self.conn_manager = conn_manager
        self.server_vars = server_vars
        self.global_vars = global_vars
        if isinstance(address, tuple):
            self.filename = '%s:%s' % (address)
        else:
            self.filename = str(address)

    def run(self):
        LOG.info('start worker')
        with self.conn_manager as conn:
            self.serve_forever(conn)
        LOG.info('exit')

    def serve_forever(self, conn):
        conn.send(self.VERSION_INFO)
        while not self.server_vars.exit.is_set():
            if self.process_request(conn):
                break

    def process_request(self, conn):
        try:
            request = conn.recv()
        except EOFError:
            return True

        command = request.get('command')
        LOG.info('receive command %r', command)
        if not command:
            conn.send(self.ERROR_REQUIRE_COMMAND)
            return

        handler = {
            'shutdown': self.do_shutdown,
            'close': self.do_close,
            'server_set': self.do_server_set,
            'get': self.do_get,
            'set': self.do_set,
            'del': self.do_del,
            'execute': self.do_execute,
            'call': self.do_call,
        }.get(command)
        if handler is None:
            LOG.warning('unknown command %r', command)
            conn.send({'error': 'unknown command', 'command': command})
            return

        try:
            return handler(conn, request)
        except Exception as exc:
            conn.send({'error': 'uncaught exception', 'exception': str(exc)})
            raise

    def do_shutdown(self, conn, _):
        self.server_vars.exit.set()
        conn.send(self.OKAY)

    def do_close(self, conn, _):
        conn.send(self.OKAY)
        return True

    def do_server_set(self, conn, request):
        name = request.get('name')
        if not name:
            conn.send(self.ERROR_REQUIRE_NAME)
            return
        if 'value' not in request:
            conn.send(self.ERROR_REQUIRE_VALUE)
            return
        if name == 'graceful_shutdown':
            if request['value']:
                self.server_vars.wait.set()
            else:
                self.server_vars.wait.clear()
        else:
            conn.send({'error': 'unknown variable name', name: name})
            return
        conn.send(self.OKAY)

    def do_get(self, conn, request):
        name = request.get('name')
        if not name:
            conn.send(self.ERROR_REQUIRE_NAME)
            return
        if name not in self.global_vars:
            conn.send({'error': 'undefined variable', 'name': name})
            return
        conn.send({'name': name, 'value': self.global_vars[name]})

    def do_set(self, conn, request):
        name = request.get('name')
        if not name:
            conn.send(self.ERROR_REQUIRE_NAME)
            return
        if 'value' not in request:
            conn.send(self.ERROR_REQUIRE_VALUE)
            return
        self.global_vars[name] = request['value']
        conn.send(self.OKAY)

    def do_del(self, conn, request):
        name = request.get('name')
        if not name:
            conn.send(self.ERROR_REQUIRE_NAME)
            return
        if name not in self.global_vars:
            conn.send({'error': 'undefined variable', 'name': name})
            return
        del self.global_vars[name]
        conn.send(self.OKAY)

    def do_execute(self, conn, request):
        if 'source' not in request:
            conn.send(self.ERROR_REQUIRE_SOURCE)
            return
        source = request['source']
        filename = request.get('filename', self.filename)
        try:
            code = compile(source, filename, 'exec')
        except SyntaxError as exc:
            LOG.exception('syntax error in %s', filename)
            conn.send({
                'error': 'syntax error',
                'filename': filename,
                'exception': str(exc),
            })
            return
        try:
            exec(code, self.global_vars)
        except Exception as exc:
            LOG.exception('runtime error in exec %s', filename)
            conn.send({
                'error': 'runtime error',
                'filename': filename,
                'exception': str(exc),
            })
            return
        conn.send(self.OKAY)

    def do_call(self, conn, request):
        name = request.get('name')
        if not name:
            conn.send(self.ERROR_REQUIRE_NAME)
            return
        if name not in self.global_vars:
            conn.send({'error': 'undefined function', 'name': name})
            return
        func = self.global_vars[name]
        args = request.get('args', ())
        kwargs = request.get('kwargs', {})
        try:
            value = func(*args, **kwargs)
        except Exception as exc:
            LOG.exception(
                'runtime error when calling %s(*%r, **%r)', name, args, kwargs)
            conn.send({
                'error': 'runtime error',
                'name': name,
                'exception': str(exc),
            })
            return
        conn.send({'name': name, 'value': value})


def closing(context_manager):
    # Some Python 2 objects are not managed.
    for attr in ('__enter__', '__exit__'):
        if not hasattr(context_manager, attr):
            return contextlib.closing(context_manager)
    return context_manager


def main(argv):
    parser = argparse.ArgumentParser(description="""
    A server that executes arbitrary Python codes.
    """)
    parser.add_argument(
        '-v', '--verbose', action='count', default=0,
        help='verbose output')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--listen-net', metavar=('ADDRESS', 'PORT'), nargs=2,
        help="""listen on AF_INET style address""")
    group.add_argument(
        '--listen-sock', metavar='PATH',
        help="""listen on AF_UNIX or AF_PIPE style path""")
    parser.add_argument(
        '--authkey-var', metavar='VAR', default='AUTHKEY',
        help="""read authkey from this environment variable
                (default %(default)s)""")
    args = parser.parse_args(argv[1:])

    if args.verbose == 0:
        level = logging.WARNING
    else:
        level = logging.INFO
    logging.basicConfig(level=level, format=LOG_FORMAT)

    if args.listen_net:
        address = (args.listen_net[0], int(args.listen_net[1]))
    else:
        address = args.listen_sock

    authkey = os.getenv(args.authkey_var)
    if authkey is None:
        parser.error('cannot read authkey from %s' % args.authkey_var)
        return 2
    if sys.version_info.major > 2:
        authkey = bytes(authkey, encoding='ascii')

    threading.current_thread().name = 'main'
    with closing(Listener(address, authkey=authkey)) as listener:
        run_server(listener)

    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
